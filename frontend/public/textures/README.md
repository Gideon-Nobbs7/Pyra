# Globe texture assets

- `earth-day-8192.webp` is an 8192×4096 WebP composite of NASA SVS's Blue Marble land and ocean layers. The source TIFFs are not shipped; `earth-day-4096.webp` is used when the GPU cannot support an 8192-pixel texture.
- `earth-bump-2048.webp` is a 2048×1024 grayscale relief-style derivative of the shaded Blue Marble surface. It is a visual bump map, not a measured elevation product.
- `earth-clouds-alpha-4096.webp` is a 4096×2048 grayscale opacity map derived from NASA SVS's CPC cloud layer, frame 01000 (2014-06-02 00:00 UTC). It is static and illustrative, not a current cloud observation.

Sources and credits:

- NASA Scientific Visualization Studio, [High Resolution Layers from “Monsoons: Wet, Dry, Repeat...”](https://svs.gsfc.nasa.gov/4439/). Blue Marble land and ocean layers; credit NASA's Scientific Visualization Studio.
- NASA Visible Earth, [Blue Marble: Clouds](https://visibleearth.nasa.gov/images/57747/blue-marble-clouds). Cloud imagery by Reto Stöckli; cloud observations from NOAA Climate Prediction Center.
- NASA imagery is public domain. NASA does not endorse Pyra.
