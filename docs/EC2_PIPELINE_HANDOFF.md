# Course2Web EC2 Pipeline Handoff

Last verified: 2026-08-10 (America/New_York)

This document records the completed migration of the Course2Web publishing
loop from a personal computer to EC2. It intentionally contains no AWS access
keys, SSH private keys, Google OAuth tokens, or other secret values.

## Current status

- The implementation branch is `codex/ec2-processing-migration`.
- The same branch is checked out on the EC2 instance.
- The branch is pushed to `origin` and the working tree was clean when this
  handoff was written.
- The first live EC2 publication succeeded. It published the 2026-08-05 and
  2026-08-07 daily homilies, updated `cp.json` and the two daily-homily podcast
  feeds, and completed the targeted CloudFront invalidation.
- The public feed and MP3 URLs returned HTTP 200 and the mutable-object hashes
  matched the generated files.
- The systemd timer is enabled. It runs two minutes after the previous run
  completes, so runs cannot overlap.
- The first timer-triggered invocation completed successfully with zero
  proposed uploads, zero validation problems, zero remote deletions, and zero
  invalidations.
- The old personal-computer `while` loop is no longer needed and should remain
  stopped.

## Infrastructure

| Component | Value |
| --- | --- |
| EC2 instance ID | `i-05ce2647b2a7504b6` |
| EC2 name | `koha-1` |
| Current public IP | `54.158.78.221` (may change) |
| EC2 OS/user | Debian 13 ARM64 / `admin` |
| EC2 repository | `/home/admin/course2web` |
| EC2 Java/pipeline directory | `/home/admin/course2web/java` |
| EC2 instance role | `ec2_role` |
| S3 bucket | `www.catholicpatrimony.com` |
| AWS region | `us-east-1` |
| CloudFront distribution | `E1KBMR7DQ2YHJZ` |
| Google Drive remote | `course2web-drive` |
| Google Drive source | `catholic/tedesche/uploads` |
| Processing cutoff | `2026-08-04`, inclusive |

The EC2 root volume is 30 GB. Approximately 22 GB was free after dependencies
were installed. The pipeline runtime used only about 27 MB after the first
publication because historical media was not downloaded.

## Safety invariants

The most important operational requirement is that the pipeline must never
delete or move files in Google Drive or S3.

- The rclone remote was authorized with `drive.readonly` scope.
- Drive input uses `rclone copyto` from remote to local paths only.
- S3 publication uses explicit, allowlisted, single-object `aws s3 cp` calls.
- S3 and rclone sync, move, purge, and deletion commands are rejected by code.
- Every run plan contains `remoteDeletes: []`.
- Dry run is the default mode.
- Real publication requires both `--mode publish` and `--allow-publish`.
- Output validation must pass before any S3 write occurs.
- CloudFront invalidation occurs only when changed objects require it.
- Source audio is copied locally and never renamed or modified in Drive.
- Audio conversion writes a temporary local file and atomically renames it
  after ffmpeg succeeds.

Do not replace the explicit upload logic with `aws s3 sync`, `rclone sync`, or
any command carrying a deletion option.

## Processing behavior

The current runtime is the standard-library Python processor in
`java/pipeline.py`; the legacy Groovy runtime is not needed on EC2.

- It reads the 13 published Google Sheet CSV tabs used by the legacy system.
- Rows dated before 2026-08-04 are preserved from the published snapshot and
  are not regenerated. An eligible `updated_on` date can intentionally bring
  an older row back into processing.
- Existing generated metadata is preserved until replacement output exists.
- Existing podcast channel formatting and historical item blocks are retained.
- New eligible podcast items are prepended or replaced by GUID.
- Podcast feeds remain capped at 50 items. Falling out of the feed does not
  delete the corresponding audio object.
- MP3s are produced by ffmpeg as 44.1 kHz mono, 256 kbps audio. ffprobe records
  the duration.
- Immutable audio receives a one-year cache policy. Mutable JSON/XML receives
  `max-age=300, must-revalidate`.
- Published objects explicitly receive `public-read`. This is currently
  required because CloudFront uses the bucket's legacy S3 website endpoint.
- Each published object stores its SHA-256 in S3 metadata. This avoids
  republishing identical multipart-uploaded MP3s whose ETags are not MD5s.
- After an entirely successful publication and invalidation, only the local
  mutable-file baseline advances atomically. This prevents repeated uploads
  and invalidations on the next timer run.

The small baseline contains only `cp.json` and two podcast XML files for each
of the four active series. No historical audio archive is copied to EC2.

## Credentials and permissions

No credentials are stored in Git.

- Local AWS credentials, if used, live in `~/.aws/credentials`.
- EC2 uses its attached IAM role instead of copied long-lived access keys.
- The rclone OAuth configuration lives at
  `/home/admin/.config/rclone/rclone.conf`, is mode 600, and must never be
  printed or committed.
- `java/pipeline.env` is mode 600 on EC2 and is ignored by Git. It contains
  runtime configuration but no access key or OAuth token.
- The EC2 role has a narrow inline policy named
  `course2web-cloudfront-invalidation` allowing only
  `cloudfront:CreateInvalidation` for distribution `E1KBMR7DQ2YHJZ`.
- The role had broad S3 permissions before this migration. The pipeline's
  command allowlist is therefore an important additional safeguard.

## Login and routine inspection

From the original local Mac, the current SSH command is:

```bash
ssh -i ~/.ssh/tedesche.pem admin@54.158.78.221
```

AWS Systems Manager Session Manager is not configured. The instance was not
registered with SSM when checked, and EC2 Instance Connect was not installed.

Once logged in:

```bash
cd /home/admin/course2web
git status --short --branch
systemctl list-timers course2web-pipeline.timer
sudo systemctl status course2web-pipeline.service
sudo journalctl -u course2web-pipeline.service -n 200 --no-pager
jq '{mode, changed: [.uploads[] | select(.changed) | .key], validationProblems, remoteDeletes, invalidations: .cloudFrontInvalidationPaths}' java/runtime/state/run-plan.json
```

The service is a oneshot, so `inactive (dead)` between successful runs is
normal. The timer should be `active` and show a next trigger time.

## Manual checks and controls

Run the tests:

```bash
cd /home/admin/course2web
java/tests/run.sh
```

Run a non-writing pipeline check:

```bash
cd /home/admin/course2web/java
./go.sh --mode dry-run
```

Disable or re-enable scheduled execution:

```bash
sudo systemctl disable --now course2web-pipeline.timer
sudo systemctl enable --now course2web-pipeline.timer
```

Reinstall changed unit files:

```bash
cd /home/admin/course2web
sudo java/scripts/install-systemd-timer.sh
```

When deploying future code changes, avoid changing the checkout while the
service is running. A conservative update sequence is:

```bash
sudo systemctl stop course2web-pipeline.timer
sudo systemctl status course2web-pipeline.service
cd /home/admin/course2web
git pull --ff-only
java/tests/run.sh
sudo java/scripts/install-systemd-timer.sh
```

## Key files

- `java/go.sh` — guarded command-line entrypoint
- `java/pipeline.py` — processor, validator, publisher, and safety allowlist
- `java/pipeline.env.example` — non-secret configuration example
- `java/PIPELINE.md` — implementation and operating documentation
- `java/scripts/capture-baseline.sh` — read-only S3 baseline capture
- `java/scripts/install-debian-dependencies.sh` — Debian dependency installer
- `java/scripts/install-systemd-timer.sh` — systemd unit installer
- `java/systemd/course2web-pipeline.service` — hardened oneshot service
- `java/systemd/course2web-pipeline.timer` — two-minute recurring timer
- `java/tests/run.sh` — full local/EC2 test entrypoint

## Git state and notable commits

The EC2 deployment currently follows `codex/ec2-processing-migration`, not
`gh-pages` or `master`. Do not switch the EC2 checkout until the migration work
has been merged or intentionally moved.

Notable commits, oldest first:

- `c189223` — Add safe pipeline migration foundation
- `e96b5cf` — Implement safe EC2 processing pipeline
- `6bde863` — Fix rclone Drive root path
- `94fdaff` — Grandfather legacy feed placeholders
- `9d9ce04` — Preserve public access for website uploads
- `3fefbc3` — Avoid republishing matching multipart objects
- `77f90a7` — Add guarded EC2 publishing timer

The remaining repository-management decision is whether and how to merge the
migration branch into the long-term active branch. The running EC2 checkout is
safe as long as `codex/ec2-processing-migration` remains available.

## Recovery notes

If a future run fails, first disable the timer and inspect the journal and
`java/runtime/state/run-plan.json`. Do not run a broad sync or deletion command
as a recovery shortcut. The last published S3 objects remain intact when local
processing or validation fails, and the local baseline advances only after the
complete publish/invalidation sequence succeeds.

If public objects unexpectedly return HTTP 403, compare their ACL with a known
historical public object. The current legacy website-origin configuration
requires the `AllUsers: READ` grant, which the uploader supplies through
`--acl public-read`.
