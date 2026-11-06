# expand_owner_groups.ps1
# Looks up every app_owner_email in the app inventory in Active Directory.
# - A distribution / security group: lists every member, including members of
#   nested groups (recursive).
# - A person: written as one row (TRUST matches people to HR itself).
# - Not found in AD: written as one row, so TRUST can show it as unmapped.
# Read-only: it only reads from AD and writes one CSV file.
#
# Needs the ActiveDirectory module (RSAT). Run in PowerShell:
#   .\expand_owner_groups.ps1
# Then upload the output CSV to TRUST on its own (Data sources).

# ===== Settings: fill these in =====
$Server        = ""                       # domain controller or domain, e.g. "dc01.corp.example.com"
$InventoryPath = ".\app_inventory.csv"    # the app inventory export (CSV)
$OwnerColumn   = "app_owner_email"        # column holding the owner email
$OutputPath    = ".\app_owner_members.csv"
# Accounts whose SAM name matches any of these patterns are treated as
# service accounts and left out (wildcards allowed, e.g. "svc*", "sa_*").
$ServiceAccountPatterns = @()
# ===================================

$ErrorActionPreference = "Stop"
if (-not $Server) { throw "Set `$Server at the top of the script first." }
Import-Module ActiveDirectory

function Escape-Ldap([string]$s) {
    # RFC 4515 escaping for values inside an LDAP filter
    $s.Replace('\', '\5c').Replace('*', '\2a').Replace('(', '\28').Replace(')', '\29').Replace([string][char]0, '\00')
}

function Get-SkipReason($u) {
    if (-not $u.Enabled) { return "disabled account" }
    foreach ($p in $ServiceAccountPatterns) {
        if ($u.SamAccountName -like $p) { return "service account (matches '$p')" }
    }
    return ""
}

$emails = Import-Csv -Path $InventoryPath |
    ForEach-Object { "$($_.$OwnerColumn)".Trim().ToLower() } |
    Where-Object { $_ } |
    Sort-Object -Unique

Write-Host "$($emails.Count) distinct owner emails to look up on $Server"
$rows = New-Object System.Collections.Generic.List[object]
$i = 0

foreach ($email in $emails) {
    $i++
    Write-Progress -Activity "Looking up owners" -Status $email -PercentComplete (100 * $i / $emails.Count)
    $e = Escape-Ldap $email
    $found = @(Get-ADObject -Server $Server `
        -LDAPFilter "(|(mail=$e)(proxyAddresses=smtp:$e))" `
        -Properties mail, sAMAccountName, objectClass)

    if ($found.Count -eq 0) {
        $rows.Add([pscustomobject]@{ owner_email = $email; owner_kind = "not found"; group_sam = ""
            member_sam = ""; member_email = ""; member_name = ""; member_enabled = ""; included = "No"; reason = "not found in AD" })
        continue
    }
    if ($found.Count -gt 1) {
        $rows.Add([pscustomobject]@{ owner_email = $email; owner_kind = "ambiguous"; group_sam = ""
            member_sam = ""; member_email = ""; member_name = ""; member_enabled = ""; included = "No"
            reason = "$($found.Count) AD objects share this email" })
        continue
    }

    $obj = $found[0]
    if ($obj.ObjectClass -eq "group") {
        # Matching-rule-in-chain: every user in the group or any nested group, in one query
        $dn = Escape-Ldap $obj.DistinguishedName
        $members = @(Get-ADUser -Server $Server `
            -LDAPFilter "(memberOf:1.2.840.113556.1.4.1941:=$dn)" `
            -Properties mail, DisplayName, Enabled)
        if ($members.Count -eq 0) {
            $rows.Add([pscustomobject]@{ owner_email = $email; owner_kind = "group"; group_sam = $obj.sAMAccountName
                member_sam = ""; member_email = ""; member_name = ""; member_enabled = ""; included = "No"; reason = "group has no members" })
        }
        foreach ($m in $members) {
            $skip = Get-SkipReason $m
            $rows.Add([pscustomobject]@{ owner_email = $email; owner_kind = "group"; group_sam = $obj.sAMAccountName
                member_sam = $m.SamAccountName; member_email = "$($m.mail)".ToLower(); member_name = $m.DisplayName
                member_enabled = $m.Enabled; included = $(if ($skip) { "No" } else { "Yes" }); reason = $skip })
        }
    }
    elseif ($obj.ObjectClass -in @("user", "inetOrgPerson")) {
        $u = Get-ADUser -Server $Server -Identity $obj.DistinguishedName -Properties mail, DisplayName, Enabled
        $skip = Get-SkipReason $u
        $rows.Add([pscustomobject]@{ owner_email = $email; owner_kind = "person"; group_sam = ""
            member_sam = $u.SamAccountName; member_email = "$($u.mail)".ToLower(); member_name = $u.DisplayName
            member_enabled = $u.Enabled; included = $(if ($skip) { "No" } else { "Yes" }); reason = $skip })
    }
    else {
        $rows.Add([pscustomobject]@{ owner_email = $email; owner_kind = $obj.ObjectClass; group_sam = ""
            member_sam = ""; member_email = ""; member_name = ""; member_enabled = ""; included = "No"
            reason = "AD object is a $($obj.ObjectClass), not a group or person" })
    }
}

$rows | Export-Csv -Path $OutputPath -NoTypeInformation -Encoding UTF8
$kinds = $rows | Group-Object owner_kind | ForEach-Object { "$($_.Name): $($_.Count) rows" }
Write-Host "Wrote $($rows.Count) rows to $OutputPath ($($kinds -join '; '))"
