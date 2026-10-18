/** The icon for each kind of place (content/cities: location ``kind``). */
import type { IconName } from "@/ui/kit";
import type { Location } from "./types";

const PLACE_ICONS: Record<NonNullable<Location["kind"]>, IconName> = {
  home: "home",
  cafe: "cafe",
  bank: "card",
  clinic: "medkit",
  library: "library",
  town_hall: "business",
  newspaper: "newspaper",
  shop: "construct",
  job_centre: "briefcase",
};

export function placeIcon(location: Location): IconName {
  return location.kind ? PLACE_ICONS[location.kind] : "location";
}
