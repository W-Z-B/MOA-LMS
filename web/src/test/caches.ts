/** A stand-in for the browser's Cache API (CacheStorage), held in memory for one test. */

import { vi } from "vitest";

class FakeCache {
  entries = new Map<string, Response>();

  async match(key: string) {
    const found = this.entries.get(String(key));
    return found ? found.clone() : undefined;
  }

  async put(key: string, response: Response) {
    this.entries.set(String(key), response.clone());
  }

  async delete(key: string) {
    return this.entries.delete(String(key));
  }

  async keys() {
    return [...this.entries.keys()].map((url) => new Request(new URL(url, "https://lms.test")));
  }
}

export function fakeCaches() {
  const stores = new Map<string, FakeCache>();
  const storage = {
    stores,
    async open(name: string) {
      if (!stores.has(name)) stores.set(name, new FakeCache());
      return stores.get(name)!;
    },
    async keys() {
      return [...stores.keys()];
    },
    async delete(name: string) {
      return stores.delete(name);
    },
    async has(name: string) {
      return stores.has(name);
    },
  };
  vi.stubGlobal("caches", storage);
  return storage;
}
