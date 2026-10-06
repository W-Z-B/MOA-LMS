import { get } from "../../api/client";
import type { Paginated } from "../../api/types";
import type { Member } from "../../api/types-marking";

/** Every student of a site (the class list comes a page at a time). */
export async function studentsOf(siteId: number): Promise<Member[]> {
  const rows: Member[] = [];
  let page = 1;
  for (;;) {
    const r = await get<Paginated<Member>>(`/sites/${siteId}/members/?page=${page}`);
    rows.push(...r.results.filter((m) => m.role === "student"));
    if (!r.next) return rows;
    page += 1;
  }
}
