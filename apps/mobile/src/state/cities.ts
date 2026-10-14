import type { CityEntry } from "@/api/types";
import { useApi } from "@/state/auth";
import { useResource, type Resource } from "@/state/resource";

/** The playable cities with their language and exam pack, from the server (no city or language is hard-coded). */
export function useCities(): Resource<CityEntry[]> {
  const api = useApi();
  return useResource(() => api.get<CityEntry[]>("/v1/world"), [api]);
}
