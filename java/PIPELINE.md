# Course2Web processing pipeline

This branch migrates the legacy workstation loop to a gated EC2 pipeline.
`go.sh` defaults to `dry-run`, which may read the published Google Sheet, copy
eligible Google Drive inputs into local work storage, and read S3 metadata. It
does not upload to S3 or invalidate CloudFront.

## Captured legacy behavior

The Phase 1 fixture at `tests/fixtures/current-behavior.json` describes the
tracked `gh-pages` output at commit
`fa4aec8d930985da9a8d96d88efac1df1ab52869`:

- `web/cp.json` is JavaScript data prefixed with `cp = ` rather than plain JSON.
- It contains 13 series and 1,458 class rows.
- The podcast template considers at most its first 50 class iterations.
- A podcast entry receives its duration, length, and generated link only when
  the generated MP3 exists in the local `build` tree.
- The MP3 URL is also the podcast GUID.
- Every generated `podcast.xml` is copied to `podcast-2.xml`.

These constraints are tests, not endorsements. Phase 2 can intentionally
replace them with snapshot-and-merge behavior while proving that historical
entries remain stable.

## Configuration precedence

Configuration is applied in this order, from lowest to highest precedence:

1. Built-in safe defaults
2. `pipeline.env` (or the file passed to `--config`)
3. Existing environment variables
4. Command-line arguments

Copy `pipeline.env.example` to `pipeline.env` for machine-local values. The
real file is ignored by Git.

For rclone, the remote root already represents Google “My Drive,” so
`GOOGLE_DRIVE_UPLOADS_PATH` begins with `catholic/` rather than `My Drive/`.

```console
$ ./go.sh
run_mode=dry-run
process_not_before=2026-08-04
external_writes=disabled
```

Use `./go.sh --config-check` to validate configuration without performing even
the read-only external calls.

## Snapshot and cutoff behavior

Run `scripts/capture-baseline.sh` to copy the current `cp.json` and podcast XML
files from S3 into the local ignored `runtime/baseline` directory. It does not
download historical media. A refresh first preserves the prior local snapshot
under `runtime/state/snapshots`.

Rows whose `date` and `updated_on` are both earlier than
`PROCESS_NOT_BEFORE` retain their baseline JSON objects exactly. Eligible rows
are merged by stable ID and may update generated metadata. Existing podcast XML
is treated as a snapshot: eligible items are prepended or replaced by GUID,
older item blocks and channel formatting are retained, and the feed is capped
at 50 items.

Audio is converted with `ffmpeg` into a temporary output and atomically renamed
inside the local work directory. Source files are never renamed or modified.

## Publication

Dry runs write `runtime/state/run-plan.json`. The plan lists every candidate
object, content hash, whether it differs from S3, cache metadata, and the exact
CloudFront paths that would be invalidated. Publish mode requires both
`--mode publish` and `--allow-publish`, revalidates output hashes, uploads with
single-object `aws s3 cp` calls, and invalidates only changed mutable or replaced
paths.

Uploads explicitly set the `public-read` object ACL because the current
CloudFront distribution uses the bucket's legacy S3 website endpoint as its
origin. Without that ACL, the website endpoint returns `403` even though the
instance role can read the object through the S3 API.

## Non-deletion invariant

The migration must not delete or move objects in Google Drive or S3. In
particular, it must never invoke:

- `rclone sync`, `move`, `delete`, `purge`, or their equivalents
- `aws s3 sync --delete`
- `aws s3 rm` or `mv`
- S3 delete-object APIs

The shared shell safety functions reject these command shapes. Phase 2 will
route all Drive and S3 operations through those checked helpers.

## Tests

Run the local Phase 1 checks from the repository root:

```console
$ java/tests/run.sh
```
