# Initial deployment

Hosting is optional for version 1. A local walkthrough or recording using `DEMO.md` is sufficient to demonstrate the app. The paid configuration below is a proposal, not a requirement or an approved expense.

The proposed first host is a Render Docker web service on the `1c-2g` plan (1 CPU, 2 GB RAM). Review the price in Render before creating it. The configuration uses one instance and one Uvicorn worker, with automatic deployments disabled.

Status: the Linux container build, Python tests, frontend tests, and production page/health checks passed on September 26, 2026 in [GitHub Actions](https://github.com/jasonorjasor/ImpactLens/actions/runs/36231189852), for commit `2205451`. This verifies the container workflow, not a live deployment or host capacity.

The `Container verification` GitHub Actions workflow builds the Linux test image, runs Python tests, builds the production image, and checks its page and `/health` using a custom port. Frontend tests run during the image build. A passing workflow run is required evidence; merely adding the workflow does not verify the image. It does not measure deployment-host capacity.

The Docker build compiles the frontend, installs Python dependencies and Git, and serves the built frontend and API together. It runs as an unprivileged user. Render supplies `PORT`; locally the container uses port 8000. `/health` is the readiness check.
Tini runs as the container's init process to forward shutdown signals and reap orphaned child processes. This matters when the disk guard or timeout stops Git and its descendants.

## Verify the container locally

With Docker installed, run from the project folder:

```powershell
docker build -t impactlens .
docker run --rm --name impactlens-preview --memory 2g --cpus 1 -p 8000:8000 impactlens
```

Open `http://127.0.0.1:8000` and run the cases in `DEMO.md`. Check `/health`, the built page and assets, and an analysis result. Stop the container before running the following benchmark commands.

Run the Python tests in the Linux test image too:

```powershell
docker build --target test -t impactlens-tests .
docker run --rm --memory 2g --cpus 1 impactlens-tests
```

Windows success does not prove that child processes are cleaned up on the deployment OS. The test image adds the test dependencies; the production image does not contain them.

## Create the Render service

After approving the hosting cost and publishing the configuration to GitHub, create a Render Blueprint from this repository. Review `render.yaml` before applying it: one Docker web service, `1c-2g`, one instance, `/health`, and manual deployments. No persistent disk is configured because cloned repositories are temporary.

## Check host capacity

From the service's shell, run the pinned commands from `benchmarks/README.md`, including the near-limit AutoGen comparison with `--requests 1`, `2`, and `3`. The benchmark starts a separate temporary API process; run it when the deployed app is idle and account for both processes in host memory metrics.

Verify matching full report hashes, zero analysis errors, two successful overlapping requests, and a quick 503 for the third. Monitor host memory and temporary disk use, and check that temporary checkouts and Git children are removed after failures. Exercise the deadline and oversized-checkout tests in the same Linux image before treating the limits as verified.
Check available temporary storage with `df -h /tmp` in the service shell. Two 100 MiB checkouts can coexist and the sampled guard can overshoot; record available space and observed peak use before setting a host disk budget.

The 2 GB plan is a starting test budget, not a proven capacity. The Windows near-limit samples reached about 393 MiB summed process RSS. Sampling can miss peaks or double-count shared pages. Keep the 100 MiB checkout limit, 120-second request deadline, and two-analysis limit until host results justify a change. One instance has at most two admitted analyses; scaling instances would multiply that total.

Sources: [Render compute plans](https://render.com/docs/compute-plans), [Docker support](https://render.com/docs/docker), and [Blueprint configuration](https://render.com/docs/blueprint-spec).
