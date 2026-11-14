import { useEffect, useId, useRef, useState, type FormEvent } from "react";

export type LockedPlace = { label: string; lat: number; lon: number; radiusKm: number; source: "place" | "coordinates" | "location" };

type PlaceFeature = {
  geometry: { coordinates: [number, number] };
  properties: Record<string, unknown>;
};

type Props = {
  areaLabel: string;
  center: { lat: number; lon: number };
  radiusKm: number;
  onLock: (place: LockedPlace) => void;
};

function featureLabel(properties: Record<string, unknown>): string {
  const parts = [properties.name, properties.city, properties.state, properties.country]
    .filter((part): part is string => typeof part === "string" && part.trim().length > 0);
  return [...new Set(parts)].join(", ") || "Unnamed place";
}

function isFeature(value: unknown): value is PlaceFeature {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  if (!item.geometry || typeof item.geometry !== "object" || !item.properties || typeof item.properties !== "object") return false;
  const coordinates = (item.geometry as { coordinates?: unknown }).coordinates;
  return Array.isArray(coordinates) && coordinates.length >= 2 &&
    typeof coordinates[0] === "number" && Number.isFinite(coordinates[0]) && Math.abs(coordinates[0]) <= 180 &&
    typeof coordinates[1] === "number" && Number.isFinite(coordinates[1]) && Math.abs(coordinates[1]) <= 90;
}

export function PlaceSearch({ areaLabel, center, radiusKm, onLock }: Props) {
  const searchId = useId();
  const listId = `${searchId}-places`;
  const [searchText, setSearchText] = useState("");
  const [suggestions, setSuggestions] = useState<PlaceFeature[]>([]);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [searchMessage, setSearchMessage] = useState("");
  const [latText, setLatText] = useState(String(center.lat));
  const [lonText, setLonText] = useState(String(center.lon));
  const [radiusText, setRadiusText] = useState(String(radiusKm));
  const [locationMessage, setLocationMessage] = useState("");
  const [pending, setPending] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const selectedLabelRef = useRef("");

  useEffect(() => {
    setLatText(String(center.lat));
    setLonText(String(center.lon));
    setRadiusText(String(radiusKm));
  }, [center.lat, center.lon, radiusKm]);

  useEffect(() => {
    const term = searchText.trim();
    if (term.length < 2 || term === selectedLabelRef.current) {
      setSuggestions([]);
      setActiveIndex(-1);
      setSearchMessage("");
      setPending(false);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setPending(true);
      const params = new URLSearchParams({ q: term, limit: "6", lang: "en" });
      void fetch(`https://photon.komoot.io/api/?${params}`, { signal: controller.signal })
        .then(async (response) => {
          if (!response.ok) throw new Error("Place search is temporarily unavailable.");
          const payload: unknown = await response.json();
          if (!payload || typeof payload !== "object" || !Array.isArray((payload as { features?: unknown }).features)) {
            throw new Error("Place search returned an invalid response.");
          }
          return (payload as { features: unknown[] }).features.filter(isFeature).slice(0, 6);
        })
        .then((features) => {
          if (controller.signal.aborted) return;
          setSuggestions(features);
          setActiveIndex(-1);
          setSearchMessage(features.length ? `${features.length} places found.` : "No places found.");
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted) return;
          setSuggestions([]);
          setSearchMessage(error instanceof Error ? error.message : "Place search failed.");
        })
        .finally(() => {
          if (!controller.signal.aborted) setPending(false);
        });
    }, 300);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [searchText]);

  const selectFeature = (feature: PlaceFeature) => {
    const [lon, lat] = feature.geometry.coordinates;
    const label = featureLabel(feature.properties);
    const typedRadius = Number(radiusText);
    const selectedRadius = Number.isFinite(typedRadius) && typedRadius >= 1 && typedRadius <= 500 ? typedRadius : radiusKm;
    onLock({ label, lat, lon, radiusKm: selectedRadius, source: "place" });
    setLatText(String(lat));
    setLonText(String(lon));
    setRadiusText(String(selectedRadius));
    selectedLabelRef.current = label;
    setSearchText(label);
    setSuggestions([]);
    setActiveIndex(-1);
    setSearchMessage(`${label} locked as the search area.`);
  };

  const submitCoordinates = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const lat = Number(latText);
    const lon = Number(lonText);
    const radius = Number(radiusText);
    if (!Number.isFinite(lat) || lat < -90 || lat > 90 || !Number.isFinite(lon) || lon < -180 || lon > 180 || !Number.isFinite(radius) || radius < 1 || radius > 500) {
      setLocationMessage("Enter latitude from -90 to 90, longitude from -180 to 180, and radius from 1 to 500 km.");
      return;
    }
    const label = `Coordinates ${lat.toFixed(3)}, ${lon.toFixed(3)}`;
    onLock({ label, lat, lon, radiusKm: radius, source: "coordinates" });
    setSearchText("");
    setLocationMessage("Coordinate area locked.");
  };

  const useLocation = () => {
    setLocationMessage("");
    if (!navigator.geolocation) {
      setLocationMessage("This browser does not provide location access. You can enter coordinates instead.");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        const label = `Current location ${coords.latitude.toFixed(3)}, ${coords.longitude.toFixed(3)}`;
        setLatText(String(coords.latitude));
        setLonText(String(coords.longitude));
        onLock({ label, lat: coords.latitude, lon: coords.longitude, radiusKm, source: "location" });
        setLocationMessage("Current location locked for this search. It is not being tracked or stored.");
      },
      (error) => {
        setLocationMessage(error.code === error.PERMISSION_DENIED
          ? "Location permission was denied. Search or enter coordinates to choose an area."
          : "Could not read your current location. Search or enter coordinates to choose an area.");
      },
      { enableHighAccuracy: false, maximumAge: 0, timeout: 10000 }
    );
  };

  return (
    <div className="area-search">
      <label className="field-label" htmlFor={`${searchId}-input`}>Search a place</label>
      <div className="place-search-wrap">
        <input
          ref={inputRef}
          id={`${searchId}-input`}
          className="place-search-input"
          type="search"
          value={searchText}
          placeholder={areaLabel || "City, landmark, or region"}
          autoComplete="off"
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={suggestions.length > 0}
          aria-controls={listId}
          aria-activedescendant={activeIndex >= 0 ? `${listId}-${activeIndex}` : undefined}
          onChange={(event) => { selectedLabelRef.current = ""; setSearchText(event.currentTarget.value); }}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown" && suggestions.length) {
              event.preventDefault(); setActiveIndex((index) => (index + 1) % suggestions.length);
            } else if (event.key === "ArrowUp" && suggestions.length) {
              event.preventDefault(); setActiveIndex((index) => (index <= 0 ? suggestions.length - 1 : index - 1));
            } else if (event.key === "Enter" && activeIndex >= 0) {
              event.preventDefault(); selectFeature(suggestions[activeIndex]);
            } else if (event.key === "Escape") {
              setSuggestions([]); setActiveIndex(-1);
            }
          }}
        />
        {pending && <span className="search-pending" aria-hidden="true">Searching</span>}
        {suggestions.length > 0 && (
          <div className="place-suggestions" id={listId} role="listbox" aria-label="Place suggestions">
            {suggestions.map((feature, index) => (
              <button key={`${feature.geometry.coordinates.join(",")}-${featureLabel(feature.properties)}`} id={`${listId}-${index}`} type="button" role="option" aria-selected={activeIndex === index} onMouseDown={(event) => event.preventDefault()} onClick={() => selectFeature(feature)}>
                  <strong>{String(feature.properties.name ?? "Unnamed place")}</strong>
                  <span>{featureLabel(feature.properties)}</span>
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="photon-attribution">Place results © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap contributors</a> · Photon</div>
      <form className="coordinate-form" onSubmit={submitCoordinates}>
        <div className="coordinate-grid">
          <label>Latitude<input aria-label="Latitude" type="number" min="-90" max="90" step="any" value={latText} onChange={(event) => setLatText(event.currentTarget.value)} /></label>
          <label>Longitude<input aria-label="Longitude" type="number" min="-180" max="180" step="any" value={lonText} onChange={(event) => setLonText(event.currentTarget.value)} /></label>
          <label>Radius km<input aria-label="Radius in kilometers" type="number" min="1" max="500" step="1" value={radiusText} onChange={(event) => setRadiusText(event.currentTarget.value)} /></label>
        </div>
        <div className="search-actions">
          <button className="small-action" type="submit">Lock coordinates</button>
          <button className="small-action secondary-action" type="button" onClick={useLocation}>Use my location</button>
        </div>
      </form>
      <div className="sr-only" aria-live="polite">{searchMessage} {locationMessage}</div>
      {(searchMessage || locationMessage) && <p className="area-feedback">{locationMessage || searchMessage}</p>}
    </div>
  );
}
