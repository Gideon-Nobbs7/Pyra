import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { apiClient } from "../../api";
import type { PlaceSuggestion } from "../../api/types";

export type LockedPlace = { label: string; lat: number; lon: number; radiusKm: number; source: "place" | "coordinates" | "location" };

type Props = {
  areaLabel: string;
  center: { lat: number; lon: number };
  radiusKm: number;
  onLock: (place: LockedPlace) => void;
};

function placeLabel(suggestion: PlaceSuggestion): string {
  const parts = [suggestion.name, suggestion.city, suggestion.state, suggestion.country]
    .filter((part): part is string => typeof part === "string" && part.trim().length > 0);
  return [...new Set(parts)].join(", ") || "Unnamed place";
}

function placeSubline(suggestion: PlaceSuggestion): string {
  const parts = [suggestion.city, suggestion.state, suggestion.country]
    .filter((part): part is string => typeof part === "string" && part.trim().length > 0);
  return [...new Set(parts)].join(", ");
}

function coordinateText(value: number): string {
  if (!Number.isFinite(value)) return "";
  return String(Math.round(value * 10000) / 10000);
}

export function PlaceSearch({ areaLabel, center, radiusKm, onLock }: Props) {
  const searchId = useId();
  const listId = `${searchId}-places`;
  const [searchText, setSearchText] = useState("");
  const [suggestions, setSuggestions] = useState<PlaceSuggestion[]>([]);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [searchMessage, setSearchMessage] = useState("");
  const [latText, setLatText] = useState(coordinateText(center.lat));
  const [lonText, setLonText] = useState(coordinateText(center.lon));
  const [radiusText, setRadiusText] = useState(String(radiusKm));
  const [locationMessage, setLocationMessage] = useState("");
  const [pending, setPending] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const selectedLabelRef = useRef("");

  useEffect(() => {
    setLatText(coordinateText(center.lat));
    setLonText(coordinateText(center.lon));
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
      void apiClient.getPlaces({ q: term, limit: 6, lang: "en" }, { signal: controller.signal })
        .then((result) => {
          if (controller.signal.aborted) return;
          if (result.data === null) {
            setSuggestions([]);
            setSearchMessage(result.message ?? "Place search failed.");
            return;
          }
          const matches = result.data.data.filter((item) =>
            Number.isFinite(item.latitude) && Number.isFinite(item.longitude) &&
            Math.abs(item.latitude) <= 90 && Math.abs(item.longitude) <= 180
          ).slice(0, 6);
          setSuggestions(matches);
          setActiveIndex(-1);
          setSearchMessage(matches.length ? `${matches.length} places found.` : "No places found.");
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

  const selectFeature = (feature: PlaceSuggestion) => {
    const { latitude: lat, longitude: lon } = feature;
    const label = placeLabel(feature);
    const typedRadius = Number(radiusText);
    const selectedRadius = Number.isFinite(typedRadius) && typedRadius >= 1 && typedRadius <= 500 ? typedRadius : radiusKm;
    onLock({ label, lat, lon, radiusKm: selectedRadius, source: "place" });
    setLatText(coordinateText(lat));
    setLonText(coordinateText(lon));
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
        setLatText(coordinateText(coords.latitude));
        setLonText(coordinateText(coords.longitude));
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
              <button key={`${feature.longitude},${feature.latitude}-${placeLabel(feature)}`} id={`${listId}-${index}`} type="button" role="option" aria-selected={activeIndex === index} onMouseDown={(event) => event.preventDefault()} onClick={() => selectFeature(feature)}>
                  <strong>{feature.name ?? "Unnamed place"}</strong>
                  <span>{placeSubline(feature) || placeLabel(feature)}</span>
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
