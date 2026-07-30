# Contributing to Gather HQs

This guide applies to human contributors and AI coding assistants.

## Before changing code

1. Read `PRODUCT_VISION.md`.
2. Check `DEVELOPMENT_ROADMAP.md` for current priorities and dependencies.
3. Review the responsible Django app and existing tests.
4. Define the user, workflow, tenant boundary, permissions, failure states, and deployment impact.
5. Avoid broad refactors in the same change as a new feature unless required.

## Development standards

- Keep views thin; place reusable domain behavior in services.
- Use explicit, descriptive names.
- Reuse shared permission and tenant-scoping helpers.
- Avoid hidden side effects in model `save()` methods when explicit services or signals with clear tests are safer.
- Use database constraints for invariants where appropriate.
- Add indexes for frequent tenant/filter/order combinations.
- Paginate unbounded lists.
- Validate all user-controlled input server-side.
- Do not expose secrets, provider payloads, or sensitive contact data in logs.
- Maintain backward-compatible migrations whenever practical.

## Tenant and permission requirements

Every organization-owned feature must include tests for:

- Authorized access by the intended role
- Denial for authenticated users outside the organization
- Denial for lower roles when applicable
- Anonymous behavior
- Cross-tenant object-ID substitution
- File/export/API access where applicable

Never rely on hidden buttons or navigation links as authorization.

## Migration practices

- Generate focused migrations.
- Review SQL and locking risk for production-sized tables.
- Separate large data migrations from schema changes when needed.
- Make data migrations resumable or idempotent where practical.
- Document required migration order and deployment caveats.
- Do not edit an already-deployed migration unless the deployment history is explicitly reset.

## Testing requirements

A change is incomplete without relevant tests. Use:

- Unit tests for services and validation
- Request/integration tests for workflows
- Permission and tenant-isolation tests
- Background-task tests
- Webhook/provider tests
- Regression tests for fixed defects
- Responsive and accessibility review for UI work

Run the commands defined by the project environment. At minimum, run Django system checks and the relevant test modules; run the full suite before release.

## UI requirements

- Use the shared layout and design components.
- Provide useful empty states and next actions.
- Preserve keyboard access and visible focus.
- Label fields and validation errors clearly.
- Confirm destructive actions.
- Support narrow mobile screens.
- Add pagination, search, filters, and sorting where the dataset can grow.
- Avoid exposing advanced configuration during the default onboarding path.

## Documentation requirements

Update as applicable:

- `CHANGELOG.md`
- `DEVELOPMENT_ROADMAP.md`
- `README.md`
- `ARCHITECTURE.md`
- `TESTING_CHECKLIST.md`
- Environment-variable and deployment instructions

## Completion checklist

- [ ] Scope matches product vision and roadmap.
- [ ] Tenant ownership and permission rules are explicit.
- [ ] Database migration is reviewed.
- [ ] Tests cover success, failure, and unauthorized cases.
- [ ] Empty, loading, error, and large-data states are considered.
- [ ] Mobile and accessibility behavior is reviewed.
- [ ] Background work is idempotent and observable where applicable.
- [ ] Documentation and changelog are updated.
- [ ] No secrets, debug output, temporary files, or generated local artifacts are committed.
