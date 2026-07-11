import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const ts = require("../frontend/node_modules/typescript");
const equalityOperators = new Set([
  ts.SyntaxKind.EqualsEqualsToken,
  ts.SyntaxKind.ExclamationEqualsToken,
  ts.SyntaxKind.EqualsEqualsEqualsToken,
  ts.SyntaxKind.ExclamationEqualsEqualsToken,
]);

const input = await readInput();
if (!input || !Array.isArray(input.files)) {
  process.exitCode = 2;
} else {
  const files = input.files.map(parseFile);
  process.stdout.write(JSON.stringify({ files }));
}

async function readInput() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch {
    return null;
  }
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
      assignments: [],
      pureStringLiterals: [],
    };
  }

  const assignments = [];
  const assignmentKeys = new Set();
  const pureStringLiterals = [];
  visit(source);
  return { path, ok: true, assignments, pureStringLiterals };

  function visit(node) {
    collectAssignment(node);
    if (
      (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) &&
      isPureStringExpression(node)
    ) {
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
      for (const key of declarationKeys(node.name)) {
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
  const targets = targetKeys(node);
  if (targets.length) return targets;
  const key = propertyKey(node);
  return key ? [key] : [];
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
