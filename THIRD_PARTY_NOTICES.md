# Third-Party Notices

This project uses third-party dependencies and may interoperate with external
OSINT tools. Third-party software remains governed by its own license terms.

## JavaScript Dependencies

Frontend dependencies are declared in `frontend/package.json` and locked in
`frontend/package-lock.json`.

Notable direct dependencies include:

- React
- React DOM
- Vite
- TypeScript
- Marked
- Lucide React
- Vitest

Review the installed dependency tree before redistribution or commercial
delivery:

```bash
cd frontend
npm install
npm ls --all
```

## Python Dependencies

Backend Python metadata is declared in `backend/pyproject.toml`.

The current lightweight runtime primarily uses the Python standard library plus
project-local modules. Some declared dependencies may be retained for future
deployment modes.

## External OSINT Tools

The project contains adapters for tools such as Sherlock, Maigret, Socialscan,
theHarvester, Amass, SpiderFoot, Recon-ng, GHunt, PhoneInfoga, Profile Parser,
and Company News workflows.

These tools are not licensed by this project unless explicitly bundled. Install
and use each tool only under its own license, terms of service, and legal
operating constraints.

## Operator Responsibility

Before shipping a customer build or production deployment, review dependency
licenses, tool terms, and data-handling obligations for the target environment.

