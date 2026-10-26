import { defineRailway, project, service, volume } from "railway/iac";
// This repository manages only its own resources in the environment. Other
// repositories export their own partial name.
// See https://docs.railway.com/infrastructure-as-code#multi-repo-projects
export const partial = "muse2api";
export default defineRailway(() => {
  const data = volume("muse2api-volume", { region: "us-west2", sizeMB: 5000 });
  const muse2api = service("muse2api", {
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    healthcheck: "/healthz",
    healthcheckTimeout: 120,
    replicas: { "us-west2": 1 },
    volumeMounts: { "/app/data": data },
  });

  return project("muse2api-cloud", {
    variables: { managed: false },
    resources: [data, muse2api],
  });
});
