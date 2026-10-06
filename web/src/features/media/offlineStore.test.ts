import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { fakeCaches } from "../../test/caches";
import { fakeServer, offline } from "../../test/fetch";
import {
  canKeep,
  clearOffline,
  describeModule,
  keepModule,
  keptModules,
  onKeptChange,
  removeModule,
  setOfflineOwner,
  spaceLeft,
  type OfflineManifest,
} from "./offlineStore";

const manifest = (module: number, files: OfflineManifest["files"]): OfflineManifest => ({
  module,
  title: `Week ${module}`,
  site: 9,
  site_title: "Introduction to Crop Production",
  files,
  total_bytes: files.reduce((sum, f) => sum + f.size, 0),
  left_out: [],
});

const weekOne = manifest(1, [
  { url: "/sites/9/contents/", kind: "data", title: "Course", size: 4096 },
  { url: "/content/11/", kind: "page", title: "Soil texture", size: 5000 },
  { url: "/videos/12/play/low/", kind: "video", title: "Soil profiles", size: 12 },
]);

describe("modules kept to read offline (item 4.03)", () => {
  let stores: ReturnType<typeof fakeCaches>;
  beforeEach(async () => {
    stores = fakeCaches();
    await setOfflineOwner(7);
  });
  afterEach(() => setOfflineOwner(null));

  it("keeps every file under the signed-in person's own cache, fetched without recording progress", async () => {
    const { calls } = fakeServer({
      "GET /sites/9/contents/": { body: { site: { id: 9 } } },
      "GET /content/11/": { body: { id: 11, title: "Soil texture" } },
      "GET /videos/12/play/low/": { body: "video" },
    });
    const progress: number[] = [];
    const kept = await keepModule(weekOne, (bytes) => progress.push(bytes));
    expect(calls.map((c) => c.path).sort()).toEqual(["/content/11/?offline=1", "/sites/9/contents/?offline=1", "/videos/12/play/low/?offline=1"]);
    expect(progress).toHaveLength(3);
    expect(kept).toMatchObject({ module: 1, title: "Week 1", files: 3, siteTitle: "Introduction to Crop Production" });
    const mine = stores.stores.get("gsa-lms-offline-7")!;
    expect(await (await mine.match("/api/v1/content/11/"))!.json()).toEqual({ id: 11, title: "Soil texture" });
    expect((await keptModules()).map((m) => m.module)).toEqual([1]);
    expect(await (await stores.stores.get("gsa-lms-owner")!.match("/__owner"))!.text()).toBe("7");
  });

  it("removes a module but keeps what another kept module also uses", async () => {
    fakeServer({
      "GET /sites/9/contents/": { body: {} },
      "GET /content/11/": { body: {} },
      "GET /videos/12/play/low/": { body: "v" },
      "GET /content/21/": { body: {} },
    });
    await keepModule(weekOne);
    await keepModule(manifest(2, [weekOne.files[0], { url: "/content/21/", kind: "page", title: "Irrigation", size: 10 }]));
    let told = 0;
    const off = onKeptChange(() => told++);
    await removeModule(1);
    off();
    const mine = stores.stores.get("gsa-lms-offline-7")!;
    expect(await mine.match("/api/v1/content/11/")).toBeUndefined();
    expect(await mine.match("/api/v1/sites/9/contents/")).toBeDefined();
    expect((await keptModules()).map((m) => m.module)).toEqual([2]);
    expect(told).toBe(1);
  });

  it("leaves nothing half kept when the connection drops, and says so", async () => {
    fakeServer({ "GET /sites/9/contents/": { body: {} }, "GET /content/11/": offline, "GET /videos/12/play/low/": { status: 404 } });
    await expect(keepModule(weekOne)).rejects.toThrow(/connection was lost|could not be fetched/);
    expect(await keptModules()).toEqual([]);
    expect(stores.stores.get("gsa-lms-offline-7")!.entries.size).toBe(0);
  });

  it("removes what an earlier person kept when someone else signs in, and everything at sign-out", async () => {
    fakeServer({ "GET /sites/9/contents/": { body: {} }, "GET /content/11/": { body: {} }, "GET /videos/12/play/low/": { body: "v" } });
    await keepModule(weekOne);
    await setOfflineOwner(null); // the session ended: their modules wait for them
    expect(stores.stores.has("gsa-lms-offline-7")).toBe(true);
    expect(await keptModules()).toEqual([]);
    await setOfflineOwner(7);
    expect((await keptModules()).length).toBe(1);
    await setOfflineOwner(8); // someone else on the same phone
    expect(stores.stores.has("gsa-lms-offline-7")).toBe(false);
    await keepModule(manifest(3, [])).catch(() => undefined);
    await clearOffline();
    expect([...stores.stores.keys()].filter((k) => k.startsWith("gsa-lms-offline-"))).toEqual([]);
    expect(await stores.stores.get("gsa-lms-owner")!.match("/__owner")).toBeUndefined();
    await expect(keepModule(weekOne)).rejects.toThrow("Sign in to keep a module");
  });

  it("asks the server what a module needs, and the browser how much room is left", async () => {
    fakeServer({ "GET /offline/modules/1/": { body: weekOne } });
    expect(await describeModule(1)).toEqual(weekOne);
    expect(await spaceLeft()).toBeNull(); // jsdom has no storage estimate
    expect(canKeep()).toBe(true);
  });
});
