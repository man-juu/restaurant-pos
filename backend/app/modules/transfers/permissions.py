VIEW = "transfers.transfer.view"
REQUEST = "transfers.transfer.request"
APPROVE = "transfers.transfer.approve"  # approve (may edit quantities) and ship
RECEIVE = "transfers.transfer.receive"

ALL = (VIEW, REQUEST, APPROVE, RECEIVE)

# docs/03 matrix: "Request transfer", "Approve and ship transfer", "Receive transfer":
# owner/co-owner Y, manager O, warehouse O. Who does what is per tenant: roles are editable.
_ALL = (VIEW, REQUEST, APPROVE, RECEIVE)
ROLE_TEMPLATES: dict[str, tuple[str, ...]] = {
    "manager": _ALL,
    "warehouse": _ALL,
    "kitchen": (VIEW,),
    "viewer": (VIEW,),
}
