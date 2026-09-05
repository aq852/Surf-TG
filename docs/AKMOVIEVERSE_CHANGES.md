# AkMovieVerse upgrade record

AkMovieVerse remains GPL-3.0 software derived from `weebzone/Surf-TG`. Original authorship is preserved in the repository history and license.

## Maintained by aq852

The `aq852/Surf-TG` evolution introduced:

- rebuilt responsive interface with separate viewer and administrator controls;
- correct HTTP byte-range planning and signed, expiring media capabilities;
- fixed Pyrofork event-loop startup and shutdown;
- automatic and historical Telegram indexing with incremental MongoDB persistence;
- normalized Telegram identifiers and duplicate-safe upserts;
- AkMovieVerse branding and original logo asset;
- custom channel image uploads;
- filename promotion/link cleanup;
- indexed-file deletion, free/premium classification, and download-action controls;
- database-backed individual viewer accounts with PBKDF2 password hashes;
- account password reset, tier/status editing, and automatic UTC-date expiry;
- display-only indexed filename renaming and channel-wide index cleanup;
- midnight, cinema, ocean, and light themes;
- optional ad placements without bundled tracking code;
- regression tests covering security, ranges, UI, indexing, and cleanup.

Implementation was developed collaboratively with OpenAI Codex. Product direction and repository ownership belong to aq852.
