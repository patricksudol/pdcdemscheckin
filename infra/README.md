# Alternative AWS deployment

Render is the primary deployment target; see the root `render.yaml` and deployment section in the
main README. These notes describe the more involved AWS alternative.

The application is packaged as one container for AWS App Runner. PostgreSQL runs in a private
Amazon RDS instance and is reached through an App Runner VPC connector.

## Required resources

- ECR repository for the application image
- App Runner service with `/api/health` as its health check
- VPC with public and private subnets in at least two availability zones
- NAT egress from the private application subnets (required for Google OAuth)
- App Runner VPC connector and security group
- Private RDS PostgreSQL instance and database security group
- Secrets Manager secret containing `PDC_DATABASE_URL`, `PDC_SESSION_SECRET`,
  `PDC_GOOGLE_CLIENT_ID`, `PDC_GOOGLE_CLIENT_SECRET`, and `PDC_ADMIN_ALLOWLIST`
- Route 53 CNAME/alias and App Runner custom-domain association for
  `checkins.phoenixvilledems.org`

RDS should use encryption, deletion protection, automated backups, and point-in-time recovery.
Permit port 5432 only from the App Runner connector security group. Do not make the database
publicly accessible.

The App Runner instance role needs read access only to the named Secrets Manager secret. Supply
secrets through App Runner runtime secret environment variables rather than build arguments.

## Wix

Add a Check In navigation item or a Wix `/checkin` page that redirects to
`https://checkins.phoenixvilledems.org`. DNS for the subdomain must point to the App Runner custom
domain validation target; the apex Wix records remain unchanged.
