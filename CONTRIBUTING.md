# Contributing to Sirina

Thanks for your interest! Bug reports, ideas and pull requests are welcome.

## Reporting bugs and ideas

Open an [issue](https://github.com/st3v3y/sirina/issues) with:

- what you did, what you expected and what happened;
- your operating system and version (and, on a Mac, the model);
- the transcription engine and AI provider in use (Settings);
- relevant log lines, with transcript text or personal data removed.

Please don't attach recordings of other people.

## Pull requests

1. For anything larger than a small fix, open an issue first so we can agree on the approach.
   Bigger changes are planned as [OpenSpec](https://github.com/Fission-AI/OpenSpec) changes in
   `openspec/changes/` (proposal, design, tasks).
2. Branch from `main` and keep each pull request focused on one change.
3. Add or update tests, and make sure these pass:

   ```bash
   cd backend && uv run pytest
   cd frontend && npm run lint && npm run build
   ```

   If you change a Swift helper, run its `build.sh`, which also runs the smoke test. If you
   change the Rust capture helper, run `cargo test` in `native/system-audio-capture-rs/`.
4. Update the README or `docs/` if behaviour or setup changes.
5. Use [Conventional Commit](https://www.conventionalcommits.org) messages, for example
   `fix(recording): …` or `feat(transcript): …`.

See the [Development](README.md#development) section of the README for setup.

## License of contributions

Sirina is licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE.md). By submitting
a contribution, you confirm that you have the right to submit it. You agree that it is licensed
under the same license, and that the maintainer may also license it under other terms,
including commercial licenses for Sirina.
