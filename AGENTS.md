
# Engineering Guidelines

## Project principles
- Correctness over implementation speed.
- Prefer simple, explicit implementations.
- Avoid unnecessary abstractions.
- Preserve existing working behavior.
- Never introduce dependencies without justification.

## Architecture
- Follow the documented architecture.
- Keep business logic separate from transport/UI logic.
- Database access must go through established data-access boundaries.
- Validate all external inputs.
- Never expose secrets or internal errors.

## Development workflow
Before implementing:
1. Understand the relevant existing code.
2. Identify affected modules and dependencies.
3. Define expected behavior.
4. Identify regression risks.

After implementing:
1. Run relevant tests.
2. Run type checking.
3. Run linting.
4. Run production build.
5. Review the complete diff.
6. Report what was changed and what remains unverified.

## Strict rules
- Do not silently change API contracts.
- Do not modify database schemas without migrations.
- Do not delete tests to make builds pass.
- Do not suppress TypeScript errors with `any` or `@ts-ignore` without justification.
- Do not claim a test passed unless it was actually executed.
- Do not refactor unrelated modules.
