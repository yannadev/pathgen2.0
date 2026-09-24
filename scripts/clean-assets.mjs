import { rmSync } from "node:fs";

rmSync("static/dist", { force: true, recursive: true });
