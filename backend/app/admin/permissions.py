"""The permission map: which role may do what on /api/admin. Kept in step with docs/permissions.md (a test checks).

Every /api/admin route declares one permission (or PUBLIC for the login itself); a route that declares nothing is
refused for everyone (deny by default). A staff member's permissions are the union of their roles'.
"""

from enum import StrEnum

from app.admin.models import RoleCode


class Perm(StrEnum):
    self_service = "self"  # any signed-in staff: own profile, logout, own password
    staff_read = "staff.read"
    staff_manage = "staff.manage"  # create staff, change roles, deactivate, unlock, reset two-factor
    audit_read = "audit.read"
    requests_read = "requests.read"  # mechanic requests, phone numbers masked
    requests_contact = "requests.contact"  # ... with the customer's full phone number
    requests_update = "requests.update"  # status changes
    customers_read = "customers.read"  # customer accounts, phone numbers masked
    customers_contact = "customers.contact"  # show one customer's full phone number (each time audited)
    content_read = "content.read"  # generated questions, photo labels
    content_review = "content.review"  # approve / reject generated questions
    datasets_manage = "datasets.manage"  # upload a category file, evaluate, publish, discard, roll back
    datasets_override = "datasets.override"  # publish although the eval gate blocks it (written reason, audited)
    knowledge_edit = "knowledge.edit"  # edit knowledge in a draft version, sign items off, review generated questions
    vehicles_manage = "vehicles.manage"  # the car catalogue and the unlisted-vehicles queue (live, audited)


PUBLIC = "public"  # no login needed (only the staff login itself)

ROLE_PERMISSIONS: dict[RoleCode, frozenset[Perm]] = {
    RoleCode.super_admin: frozenset(Perm),
    RoleCode.content_admin: frozenset(
        {
            Perm.self_service,
            Perm.content_read,
            Perm.content_review,
            Perm.datasets_manage,
            Perm.knowledge_edit,
            Perm.vehicles_manage,
        }
    ),
    RoleCode.support_agent: frozenset(
        {
            Perm.self_service,
            Perm.requests_read,
            Perm.requests_contact,
            Perm.requests_update,
            Perm.customers_read,
            Perm.customers_contact,
        }
    ),
    RoleCode.mechanic: frozenset({Perm.self_service, Perm.requests_read}),
    RoleCode.customer: frozenset(),  # customers never get into /api/admin
}


def permissions_for(roles: list[str]) -> frozenset[Perm]:
    out: set[Perm] = set()
    for r in roles:
        if r in RoleCode.__members__:
            out |= ROLE_PERMISSIONS[RoleCode(r)]
    return frozenset(out)
