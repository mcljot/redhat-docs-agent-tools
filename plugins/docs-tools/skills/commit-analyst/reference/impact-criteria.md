# Documentation Impact Grading Framework

Grade each code change to determine documentation impact level and required actions.

## Impact grades

| Grade | Criteria | Examples |
|-------|----------|----------|
| **HIGH** | Major new features, architecture changes, new APIs, breaking changes, new user-facing workflows, new integrations | New operator install method, API v2 migration, new UI dashboard, new authentication provider |
| **MEDIUM** | Enhancements to existing features, new configuration options, changed defaults, deprecations, performance changes with user-visible impact | New CLI flag, updated default timeout, deprecated parameter, new supported platform |
| **LOW** | Minor UI text changes, small behavioral tweaks, additional supported values, error message improvements | New enum value, updated error message text, minor UX adjustment |
| **NONE** | Internal refactoring, test-only changes, CI/CD changes, dependency bumps, code cleanup, linting fixes | Test coverage increase, linter fixes, internal module rename, build script update |

## Special handling

- **QE/testing issues**: Grade as NONE unless they reveal user-facing behavioral changes
- **Security fixes (CVEs)**: Grade as HIGH if they require user action (config change, upgrade steps); MEDIUM if the fix is automatic
- **Bug fixes**: Grade based on whether the fix changes documented behavior or introduces new workarounds
- **Deprecations**: Grade as MEDIUM minimum — users need migration guidance even for soft deprecations

## Signal-to-grade mapping

Map signals from code analysis to minimum impact grades:

| Signal | Minimum grade | Rationale |
|--------|--------------|-----------|
| New public API endpoint or route | HIGH | Users need to know how to call it |
| New file in api/, controllers/, handlers/ | HIGH | New user-facing surface area |
| Breaking change indicator (BREAKING, removed, migration) | HIGH | Users must take action |
| New configuration parameter or environment variable | MEDIUM | Users may need to set it |
| Changed default value | MEDIUM | Existing behavior changes silently |
| Deprecated function/parameter/endpoint | MEDIUM | Users need migration path |
| New file in source code (non-API) | MEDIUM | May indicate new capability |
| Schema change (protobuf, GraphQL, OpenAPI) | MEDIUM-HIGH | Contract change for consumers |
| Existing docs reference changed code | MEDIUM | Docs may be inaccurate |
| Config file structure change | MEDIUM | Users with custom configs affected |
| Test-only changes | NONE | No user-facing impact |
| CI/CD pipeline changes | NONE | Internal tooling |
| Dependency updates (no API change) | NONE | Transparent to users |
| Internal refactoring (no behavior change) | NONE | Implementation detail |

## Documentation action categories

Based on impact grade, determine what documentation actions are needed:

| Change type | Typical actions |
|------------|----------------|
| New feature | Create Concept + Procedure + Reference modules |
| New API | Create Reference module (endpoints, parameters, responses) + Procedure (usage example) |
| Enhancement | Update existing Procedure or Reference module |
| Breaking change | Update existing modules + add migration Procedure |
| Deprecation | Update existing modules with deprecation notice + migration guidance |
| Config change | Update Reference module (parameters table) |
| Bug fix (behavior change) | Update Procedure or Concept if documented behavior changes |
| New integration | Create Concept (overview) + Procedure (setup) + Reference (configuration) |

## Aggregate grading

When a change spans multiple files and categories, the overall grade is the **highest individual grade** found. A single HIGH-signal file makes the entire change HIGH impact, even if other files are NONE.

However, consider the change holistically:
- A new test file alongside a new API file confirms the API is intentional, not experimental
- Documentation files already modified in the same change may reduce the urgency (docs are being updated in-flight)
- Changes to generated code (`.pb.go`, `.gen.go`) inherit the grade of the schema that generated them, not their own
