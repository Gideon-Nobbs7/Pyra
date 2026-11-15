import type { RefObject } from "react";

export type GlobeObservation = {
  id: string;
  source: "modis" | "viirs";
  observedAt: string;
  ingestedAt: string;
  latitude: number;
  longitude: number;
  confidence: string | null;
  frp: number | null;
  frpUnit: string | null;
};

export type GlobeViewProps = {
  containerRef: RefObject<HTMLDivElement | null>;
  observations: GlobeObservation[];
  selectedObservationId: string | null;
  onSelectObservation: (observationId: string | null) => void;
  zoomRequest?: {
    direction: "in" | "out";
    requestId: number;
  };
  resetRequestId?: number;
  flyTo?: {
    lat: number;
    lon: number;
    requestId: number;
  };
  onReady?: () => void;
};
