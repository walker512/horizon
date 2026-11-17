# Security boundary

Horizon is a single-user loopback application for supplied text. The browser does not fetch source URLs, send data to an AI provider, or publish briefings. The separate `horizon.radar collect --allow-network` CLI sends your saved search query to the official public GitHub API; it never follows redirects or sends an account token. Do not place secrets in search queries. See docs/GITHUB_RADAR.md for its explicit network boundary. Host checks and Origin checks protect ordinary browser access; JSON is required for write endpoints. This is not authentication for a multi-user deployment. Never expose it through a public reverse proxy.

Use only content you have permission to process. Avoid pasting credentials, private conversations, patient data or identifying information. URLs may contain sensitive query strings. Project JSON and briefing exports include supplied data and notes. No automatic redaction, encryption, copyright clearance or fact verification is provided.

RSS/Atom files with DTD/entity declarations are rejected. Imported article markup is reduced to text; HTML briefs escape source-derived content and contain no scripts or remote assets. Portable project import validates record relationships and hashes and resets editorial approvals, but cannot authenticate who wrote the supplied history.

Snapshots are immutable through the application API. Hashes and logs are local integrity aids, not tamper-proof attestations. A user with filesystem access can alter the database or exported JSON. Keep backups before moving your workspace.

Limitations and defects should be reproduced with fictional content rather than real personal data. This source release does not designate a private vulnerability-reporting channel; do not include secrets in public reports or send them to guessed addresses.
