import { createRequire } from "node:module";

const limits = {
  inputBytes: boundedLimit("PUBLIC_RELEASE_AST_MAX_INPUT_BYTES", 2 * 1024 * 1024),
  fileBytes: boundedLimit("PUBLIC_RELEASE_AST_MAX_FILE_BYTES", 512 * 1024),
  files: boundedLimit("PUBLIC_RELEASE_AST_MAX_FILES", 64),
  outputBytes: boundedLimit("PUBLIC_RELEASE_AST_MAX_OUTPUT_BYTES", 4 * 1024 * 1024),
  assignments: boundedLimit("PUBLIC_RELEASE_AST_MAX_ASSIGNMENTS", 20_000),
  literals: boundedLimit("PUBLIC_RELEASE_AST_MAX_LITERALS", 20_000),
};
const ts = loadTypeScript();
if (!ts) {
  await writeOutput({ error: "typescript_missing", files: [] });
  process.exit(0);
}
const equalityOperators = new Set([
  ts.SyntaxKind.EqualsEqualsToken,
  ts.SyntaxKind.ExclamationEqualsToken,
  ts.SyntaxKind.EqualsEqualsEqualsToken,
  ts.SyntaxKind.ExclamationEqualsEqualsToken,
]);

const inputResult = await readInput();
if (inputResult.error) {
  await writeOutput({ error: inputResult.error, files: [] });
} else {
  const input = inputResult.value;
  if (
    !input ||
    typeof input !== "object" ||
    Array.isArray(input) ||
    Object.keys(input).length !== 1 ||
    !Array.isArray(input.files) ||
    input.files.length > limits.files ||
    input.files.some((entry) =>
      !entry ||
      typeof entry !== "object" ||
      Array.isArray(entry) ||
      Object.keys(entry).sort().join(",") !== "path,text" ||
      typeof entry.path !== "string" ||
      typeof entry.text !== "string"
    )
  ) {
    await writeOutput({ error: "invalid_schema", files: [] });
    process.exit(0);
  }
  if (input.files.some((entry) => Buffer.byteLength(entry.text, "utf8") > limits.fileBytes)) {
    await writeOutput({ error: "input_limit", files: [] });
    process.exit(0);
  }
  const files = input.files.map(parseFile);
  await writeOutput({ files });
}

async function readInput() {
  const chunks = [];
  let size = 0;
  let tooLarge = false;
  for await (const chunk of process.stdin) {
    size += chunk.length;
    if (size > limits.inputBytes) {
      tooLarge = true;
      continue;
    }
    chunks.push(chunk);
  }
  if (tooLarge) return { error: "input_limit" };
  try {
    return { value: JSON.parse(Buffer.concat(chunks).toString("utf8")) };
  } catch {
    return { error: "invalid_json" };
  }
}

function boundedLimit(name, fallback) {
  const value = Number.parseInt(process.env[name] ?? "", 10);
  return Number.isSafeInteger(value) && value > 0 ? Math.min(value, fallback) : fallback;
}

function loadTypeScript() {
  const roots = [import.meta.url, new URL("../frontend/package.json", import.meta.url)];
  for (const root of roots) {
    try {
      return createRequire(root)("typescript");
    } catch {
      // Try the next declared source root.
    }
  }
  return null;
}

function writeOutput(payload) {
  let output = JSON.stringify(payload);
  if (Buffer.byteLength(output, "utf8") > limits.outputBytes) {
    output = JSON.stringify({ error: "output_limit", files: [] });
  }
  return new Promise((resolve, reject) => {
    process.stdout.write(output, "utf8", (error) => {
      if (error) reject(error);
      else resolve();
    });
  });
}

function parseFile(entry) {
  const path = typeof entry?.path === "string" ? entry.path : "";
  const text = typeof entry?.text === "string" ? entry.text : "";
  const source = ts.createSourceFile(
    path,
    text,
    ts.ScriptTarget.Latest,
    true,
    scriptKind(path),
  );
  if (source.parseDiagnostics.length) {
    const position = source.parseDiagnostics[0].start ?? 0;
    return {
      path,
      ok: false,
      errorLine: source.getLineAndCharacterOfPosition(position).line + 1,
      errorCategory: "parse_error",
      assignments: [],
      pureStringLiterals: [],
    };
  }

  const assignments = [];
  const assignmentKeys = new Set();
  const pureStringLiterals = [];
  let recordLimitExceeded = false;
  visit(source);
  if (recordLimitExceeded) {
    return {
      path,
      ok: false,
      errorLine: 1,
      errorCategory: "record_limit",
      assignments: [],
      pureStringLiterals: [],
    };
  }
  return { path, ok: true, assignments, pureStringLiterals };

  function visit(node) {
    if (recordLimitExceeded) return;
    collectAssignment(node);
    if (
      (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) &&
      isPureStringExpression(node)
    ) {
      if (pureStringLiterals.length >= limits.literals) {
        recordLimitExceeded = true;
        return;
      }
      pureStringLiterals.push({ start: node.getStart(source), end: node.end });
    }
    ts.forEachChild(node, visit);
  }

  function addAssignment(key, operator, expression, target) {
    if (!key || !expression) return;
    const start = target.getStart(source);
    const valueStart = expression.getStart(source);
    const identity = JSON.stringify([key, operator, start, valueStart, expression.end]);
    if (assignmentKeys.has(identity)) return;
    if (assignments.length >= limits.assignments) {
      recordLimitExceeded = true;
      return;
    }
    assignmentKeys.add(identity);
    assignments.push({
      key,
      operator,
      start,
      valueStart,
      end: expression.end,
      safeInitializer: isSafeCredentialInitializer(expression),
    });
  }

  function collectAssignment(node) {
    if (node.initializer && node.name) {
      const operator = ts.isPropertyAssignment(node) ? ":" : "=";
      let keys;
      if (ts.isBindingElement(node)) {
        keys = bindingElementKeys(node);
      } else if (
        (ts.isVariableDeclaration(node) || ts.isParameter(node)) &&
        (ts.isObjectBindingPattern(node.name) || ts.isArrayBindingPattern(node.name))
      ) {
        keys = bindingPatternKeysWithoutDefaults(node.name);
      } else {
        keys = declarationKeys(node.name);
      }
      for (const key of keys) {
        addAssignment(key, operator, node.initializer, node.name);
      }
    }
    if (ts.isBinaryExpression(node) && isAssignmentOperator(node.operatorToken.kind)) {
      for (const key of targetKeys(node.left)) {
        addAssignment(
          key,
          ts.tokenToString(node.operatorToken.kind) ?? "=",
          node.right,
          node.left,
        );
      }
    }
  }
}

function scriptKind(path) {
  if (path.endsWith(".tsx")) return ts.ScriptKind.TSX;
  if (path.endsWith(".ts")) return ts.ScriptKind.TS;
  if (path.endsWith(".jsx")) return ts.ScriptKind.JSX;
  if (path.endsWith(".json")) return ts.ScriptKind.JSON;
  return ts.ScriptKind.JS;
}

function targetKeys(node) {
  if (ts.isIdentifier(node)) return [node.text];
  if (ts.isPropertyAccessExpression(node)) return [node.name.text];
  if (ts.isElementAccessExpression(node)) {
    return stringValue(node.argumentExpression) ? [stringValue(node.argumentExpression)] : [];
  }
  if (ts.isObjectBindingPattern(node) || ts.isArrayBindingPattern(node)) {
    return node.elements.flatMap((element) =>
      ts.isBindingElement(element) ? targetKeys(element.name) : [],
    );
  }
  return [];
}

function declarationKeys(node) {
  if (ts.isObjectBindingPattern(node) || ts.isArrayBindingPattern(node)) {
    return node.elements.flatMap((element) =>
      ts.isBindingElement(element) ? bindingElementKeys(element) : [],
    );
  }
  const targets = targetKeys(node);
  if (targets.length) return targets;
  const key = propertyKey(node);
  return key ? [key] : [];
}

function bindingElementKeys(node) {
  return node.propertyName
    ? declarationKeys(node.propertyName)
    : declarationKeys(node.name);
}

function bindingPatternKeysWithoutDefaults(node) {
  return node.elements.flatMap((element) => {
    if (!ts.isBindingElement(element) || element.initializer) return [];
    if (ts.isObjectBindingPattern(element.name) || ts.isArrayBindingPattern(element.name)) {
      return bindingPatternKeysWithoutDefaults(element.name);
    }
    return bindingElementKeys(element);
  });
}

function propertyKey(node) {
  if (ts.isIdentifier(node) || ts.isStringLiteral(node)) return node.text;
  if (ts.isPrivateIdentifier(node)) return node.text.replace(/^#/, "");
  if (ts.isComputedPropertyName(node)) return stringValue(node.expression);
  return "";
}

function stringValue(node) {
  return node && (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node))
    ? node.text
    : "";
}

function isAssignmentOperator(kind) {
  return kind >= ts.SyntaxKind.FirstAssignment && kind <= ts.SyntaxKind.LastAssignment;
}

function isSafeCredentialInitializer(node) {
  if (
    !ts.isCallExpression(node) ||
    !ts.isIdentifier(node.expression) ||
    node.expression.text !== "useState" ||
    node.arguments.length !== 1
  ) {
    return false;
  }
  const initial = node.arguments[0];
  return initial.kind === ts.SyntaxKind.NullKeyword ||
    (ts.isStringLiteral(initial) && initial.text === "");
}

function isPureStringExpression(node) {
  let current = node;
  while (ts.isParenthesizedExpression(current.parent)) current = current.parent;
  const parent = current.parent;
  if (!parent || ts.isSourceFile(parent)) return true;
  if (ts.isVariableDeclaration(parent) || ts.isParameter(parent)) {
    return parent.initializer === current;
  }
  if (ts.isPropertyAssignment(parent)) return parent.initializer === current;
  if (ts.isBinaryExpression(parent)) {
    if (
      parent.operatorToken.kind === ts.SyntaxKind.EqualsToken &&
      parent.right === current
    ) {
      return true;
    }
    return equalityOperators.has(parent.operatorToken.kind);
  }
  if (ts.isCallExpression(parent) || ts.isNewExpression(parent)) {
    return parent.arguments?.includes(current) ?? false;
  }
  if (ts.isArrayLiteralExpression(parent)) return parent.elements.includes(current);
  if (ts.isReturnStatement(parent)) return parent.expression === current;
  if (ts.isExpressionStatement(parent)) return parent.expression === current;
  if (ts.isArrowFunction(parent)) return parent.body === current;
  return false;
}
