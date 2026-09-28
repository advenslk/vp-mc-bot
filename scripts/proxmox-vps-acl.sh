#!/usr/bin/env bash
set -euo pipefail

TOKEN_ID="${1:-helzerx-bot@pam!helzerx}"
USER_ID="${TOKEN_ID%%!*}"

echo "Applying scoped Proxmox permissions for ${TOKEN_ID}..."

pveum acl modify / -user "${USER_ID}" -role PVEAuditor
pveum acl modify /vms -user "${USER_ID}" -role PVEVMAdmin
pveum acl modify /storage -user "${USER_ID}" -role PVEDatastoreUser
pveum acl modify /sdn/zones/localnetwork -user "${USER_ID}" -role PVESDNUser

pveum acl modify / -token "${TOKEN_ID}" -role PVEAuditor
pveum acl modify /vms -token "${TOKEN_ID}" -role PVEVMAdmin
pveum acl modify /storage -token "${TOKEN_ID}" -role PVEDatastoreUser
pveum acl modify /sdn/zones/localnetwork -token "${TOKEN_ID}" -role PVESDNUser

echo
echo "Effective token permissions:"
pveum user token permissions "${USER_ID}" "${TOKEN_ID##*!}"
