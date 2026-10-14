import { readdirSync, readFileSync, statSync } from "fs";
import { join, relative } from "path";

const SRC = join(__dirname, "..");

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? files(path) : /\.tsx?$/.test(name) ? [path] : [];
  });
}

/** On the web, evaluating a Skia module before CanvasKit loads breaks Skia for the whole app (the City map crashed
 * this way). Only the renderer folder may import Skia, and everything else must load the renderer lazily. */
test("Skia and the renderer are only imported lazily outside src/world/renderer", () => {
  const offenders = files(SRC)
    .filter((path) => !relative(SRC, path).startsWith("world/renderer") && !path.includes("__tests__"))
    .filter((path) => /^import [^;]*["'](@shopify\/react-native-skia|@\/world\/renderer\/[^"']+)["']/m.test(readFileSync(path, "utf8")))
    .map((path) => relative(SRC, path));
  expect(offenders).toEqual([]);
});
