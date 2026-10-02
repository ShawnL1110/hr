# Newton HR development

Before working in this repository, read `skills/newton-hr-maintainer/SKILL.md` and
its relevant references. The HR team may change HR features independently;
stuff business logic and shared-host infrastructure remain outside this repo's
publishing authority. Follow the user's current task and authorization.

Check `docs/implementation.md` for actual migration status: the initial service
is a read-only imported snapshot, not a complete writable HR replacement.
Use the restricted HR deployment channel when it has been activated by the
platform operator; never substitute a host-admin SSH key or Docker access.
Production secrets are delivered separately and must not enter Git or skill text.
