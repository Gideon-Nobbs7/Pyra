# Globe texture assets

- `earth-day-8192.webp` is an 8192×4096 daytime diffuse map derived from NASA's Blue Marble Next Generation January 2004 `world` base map (the non-shaded variant), with a separate NASA blue-ocean layer composited beneath the land. It contains no night-side mask or terminator shading. The 4096×2048 copy is selected when the GPU cannot support 8192-pixel textures. The Earth uses an unlit material, so its displayed brightness comes from this daytime texture.
- `earth-night-4096.jpg` is a 4096×2048 night-lights map (city lights on the dark side, blended in by a day/night terminator shader). Sourced from NASA SVS visualization 30003 (DMSP OLS "Earth at Night"), converted from the `dmsp_4096.png` still to quality-88 JPEG.
- `earth-clouds-alpha-4096.webp` is a 4096×2048 grayscale opacity map derived from NASA SVS's CPC cloud layer, frame 01000 (2014-06-02 00:00 UTC). It is static and illustrative, not a current cloud observation.

Sources and credits:

- NASA Earth Observatory, [Blue Marble: Next Generation base map](https://science.nasa.gov/earth/earth-observatory/blue-marble-next-generation/base-map/). January 2004 global `world.200401.3x21600x10800.jpg` (non-shaded, 2 km/pixel); credit NASA Earth Observatory and Reto Stöckli.
- NASA Scientific Visualization Studio, ["Earth at Night" (visualization 30003)](https://svs.gsfc.nasa.gov/30003/). DMSP OLS night-lights still (`dmsp_4096.png`).
- NASA Scientific Visualization Studio, [High Resolution Layers from “Monsoons: Wet, Dry, Repeat...”](https://svs.gsfc.nasa.gov/4439/). Blue-ocean layer; credit NASA's Scientific Visualization Studio.
- NASA Visible Earth, [Blue Marble: Clouds](https://visibleearth.nasa.gov/images/57747/blue-marble-clouds). Cloud imagery by Reto Stöckli; cloud observations from NOAA Climate Prediction Center.
- NASA imagery is public domain. NASA does not endorse Pyra.
