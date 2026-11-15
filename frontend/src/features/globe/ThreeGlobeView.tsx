import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import type { GlobeObservation, GlobeViewProps } from "./GlobeView";

const EARTH_RADIUS = 1.65;
const MAX_DPR = 1.5;
const EARTH_TEXTURE_8K_URL = `${import.meta.env.BASE_URL}textures/earth-day-8192.webp`;
const EARTH_TEXTURE_4K_URL = `${import.meta.env.BASE_URL}textures/earth-day-4096.webp`;
const NIGHT_TEXTURE_4K_URL = `${import.meta.env.BASE_URL}textures/earth-night-4096.jpg`;
const CLOUD_TEXTURE_4K_URL = `${import.meta.env.BASE_URL}textures/earth-clouds-alpha-4096.webp`;

/**
 * The night-earth texture is a dark blue-tinted landmass map whose city lights
 * are faint. Isolate the warm lights onto black so the night-side shader can
 * show them instead of the blue wash.
 */
function extractCityLightsTexture(image: HTMLImageElement): THREE.CanvasTexture {
  const width = image.naturalWidth || image.width;
  const height = image.naturalHeight || image.height;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) {
    throw new Error("Unable to extract city lights: no 2D canvas context.");
  }
  context.drawImage(image, 0, 0);
  const pixels = context.getImageData(0, 0, width, height);
  const data = pixels.data;
  for (let index = 0; index < data.length; index += 4) {
    const r = data[index];
    const g = data[index + 1];
    const b = data[index + 2];
    // City lights burn warm; the base map wash is blue. Pixels with no warm
    // excess go pure black so oceans stay dark on the night side.
    const warmth = Math.max(0, (r - b + (g - b)) / 2 / 255);
    const mask = Math.pow(warmth, 0.65) * 3.2;
    data[index] = Math.min(255, r * mask);
    data[index + 1] = Math.min(255, g * mask);
    data[index + 2] = Math.min(255, b * mask * 0.4);
  }
  context.putImageData(pixels, 0, 0);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.wrapS = THREE.RepeatWrapping;
  return texture;
}

function createEarthFallbackTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 1024;
  canvas.height = 512;
  const context = canvas.getContext("2d");
  if (!context) {
    throw new Error("Unable to create the procedural Earth texture.");
  }

  const ocean = context.createLinearGradient(0, 0, 0, canvas.height);
  ocean.addColorStop(0, "#1c7590");
  ocean.addColorStop(0.45, "#0b3e57");
  ocean.addColorStop(1, "#031522");
  context.fillStyle = ocean;
  context.fillRect(0, 0, canvas.width, canvas.height);

  const landmasses = [
    [[104, 152], [142, 128], [185, 140], [218, 174], [196, 205], [156, 211], [125, 193]],
    [[390, 105], [430, 86], [484, 100], [522, 136], [503, 167], [460, 163], [432, 191], [401, 170]],
    [[525, 188], [568, 203], [581, 249], [553, 293], [530, 343], [505, 316], [515, 266], [493, 225]],
    [[676, 114], [735, 96], [792, 124], [831, 166], [805, 209], [753, 218], [710, 196], [684, 161]],
    [[750, 279], [789, 295], [801, 342], [776, 387], [743, 372], [728, 323]]
  ];

  landmasses.forEach((landmass, index) => {
    context.beginPath();
    landmass.forEach(([x, y], pointIndex) => {
      if (pointIndex === 0) context.moveTo(x, y);
      else context.lineTo(x, y);
    });
    context.closePath();
    context.fillStyle = index % 2 === 0 ? "#426d58" : "#54745b";
    context.fill();
    context.strokeStyle = "rgba(151, 196, 133, 0.32)";
    context.lineWidth = 3;
    context.stroke();
  });

  context.globalAlpha = 0.22;
  for (let index = 0; index < 36; index += 1) {
    const x = (index * 173) % canvas.width;
    const y = 52 + ((index * 91) % 400);
    context.fillStyle = index % 2 === 0 ? "#d3d78d" : "#8fa878";
    context.fillRect(x, y, 42 + (index % 5) * 9, 3);
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  return texture;
}

function createStarfield(): THREE.Points {
  const count = 4200;
  const positions = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  let seed = 51327;
  const random = () => {
    seed = (seed * 16807) % 2147483647;
    return (seed - 1) / 2147483646;
  };
  const galacticNormal = new THREE.Vector3(0.22, 0.88, 0.42).normalize();
  const tangentA = new THREE.Vector3().crossVectors(galacticNormal, new THREE.Vector3(0, 0, 1)).normalize();
  const tangentB = new THREE.Vector3().crossVectors(galacticNormal, tangentA).normalize();
  const colorOptions = ["#d9eaff", "#a9cfff", "#fff1d1", "#ffffff"];

  for (let index = 0; index < count; index += 1) {
    let direction: THREE.Vector3;
    if (random() < 0.76) {
      const angle = random() * Math.PI * 2;
      const offset = (random() + random() + random() - 1.5) * 0.14;
      direction = tangentA.clone().multiplyScalar(Math.cos(angle))
        .addScaledVector(tangentB, Math.sin(angle))
        .addScaledVector(galacticNormal, offset).normalize();
    } else {
      const theta = random() * Math.PI * 2;
      const y = random() * 2 - 1;
      const radius = Math.sqrt(1 - y * y);
      direction = new THREE.Vector3(radius * Math.cos(theta), y, radius * Math.sin(theta));
    }
    const distance = 28 + random() * 8;
    positions[index * 3] = direction.x * distance;
    positions[index * 3 + 1] = direction.y * distance;
    positions[index * 3 + 2] = direction.z * distance;
    const color = new THREE.Color(colorOptions[Math.floor(random() * colorOptions.length)]);
    colors[index * 3] = color.r;
    colors[index * 3 + 1] = color.g;
    colors[index * 3 + 2] = color.b;
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  return new THREE.Points(
    geometry,
    new THREE.PointsMaterial({
      vertexColors: true,
      size: 0.045,
      sizeAttenuation: true,
      transparent: true,
      opacity: 0.9,
      depthWrite: false
    })
  );
}

function createMilkyWayBackdrop(): THREE.Mesh {
  const canvas = document.createElement("canvas");
  canvas.width = 2048;
  canvas.height = 1024;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Unable to create the starfield backdrop.");

  const night = context.createLinearGradient(0, 0, 0, canvas.height);
  night.addColorStop(0, "#03050b");
  night.addColorStop(0.48, "#07101f");
  night.addColorStop(1, "#02040a");
  context.fillStyle = night;
  context.fillRect(0, 0, canvas.width, canvas.height);

  context.save();
  context.translate(canvas.width * 0.5, canvas.height * 0.5);
  context.rotate(-0.33);
  context.shadowBlur = 80;
  context.shadowColor = "#356bb5";
  const nebula = context.createLinearGradient(0, -180, 0, 180);
  nebula.addColorStop(0, "rgba(33, 67, 125, 0)");
  nebula.addColorStop(0.35, "rgba(42, 93, 165, 0.18)");
  nebula.addColorStop(0.5, "rgba(113, 142, 194, 0.29)");
  nebula.addColorStop(0.64, "rgba(51, 88, 153, 0.16)");
  nebula.addColorStop(1, "rgba(33, 67, 125, 0)");
  context.fillStyle = nebula;
  context.fillRect(-canvas.width, -180, canvas.width * 2, 360);
  context.restore();

  let seed = 14143;
  const random = () => {
    seed = (seed * 16807) % 2147483647;
    return (seed - 1) / 2147483646;
  };
  for (let index = 0; index < 2500; index += 1) {
    const x = random() * canvas.width;
    const y = random() * canvas.height;
    const radius = random() > 0.985 ? 1.6 : 0.35 + random() * 0.65;
    const alpha = 0.24 + random() * 0.7;
    context.fillStyle = random() > 0.83
      ? `rgba(151, 190, 255, ${alpha})`
      : `rgba(231, 240, 255, ${alpha})`;
    context.beginPath();
    context.arc(x, y, radius, 0, Math.PI * 2);
    context.fill();
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const backdrop = new THREE.Mesh(
    new THREE.SphereGeometry(80, 48, 32),
    new THREE.MeshBasicMaterial({
      map: texture,
      side: THREE.BackSide,
      depthWrite: false,
      toneMapped: false
    })
  );
  backdrop.renderOrder = -2;
  return backdrop;
}

function createLensFlare(position: THREE.Vector3): THREE.Group {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 256;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Unable to create the sun flare.");

  const glow = context.createRadialGradient(128, 128, 2, 128, 128, 126);
  glow.addColorStop(0, "rgba(255,255,237,1)");
  glow.addColorStop(0.08, "rgba(255,238,186,0.95)");
  glow.addColorStop(0.22, "rgba(255,175,93,0.38)");
  glow.addColorStop(0.58, "rgba(255,132,70,0.08)");
  glow.addColorStop(1, "rgba(255,132,70,0)");
  context.fillStyle = glow;
  context.fillRect(0, 0, canvas.width, canvas.height);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;

  const flare = new THREE.Group();
  flare.position.copy(position);
  const halo = new THREE.Sprite(new THREE.SpriteMaterial({
    map: texture,
    color: "#fff2cf",
    transparent: true,
    depthTest: false,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    toneMapped: false
  }));
  halo.scale.set(1.05, 1.05, 1);
  flare.add(halo);

  const core = new THREE.Sprite(new THREE.SpriteMaterial({
    map: texture,
    color: "#fff9e8",
    transparent: true,
    depthTest: false,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    toneMapped: false
  }));
  core.scale.set(0.34, 0.34, 1);
  flare.add(core);
  flare.renderOrder = 10;
  return flare;
}

function observationPosition(observation: GlobeObservation): THREE.Vector3 {
  const latitude = THREE.MathUtils.degToRad(observation.latitude);
  const longitude = THREE.MathUtils.degToRad(observation.longitude);
  return new THREE.Vector3(
    EARTH_RADIUS * Math.cos(latitude) * Math.sin(longitude),
    EARTH_RADIUS * Math.sin(latitude),
    EARTH_RADIUS * Math.cos(latitude) * Math.cos(longitude)
  );
}

function createObservationPoints(
  observations: GlobeObservation[],
  selectedObservationId: string | null
): THREE.Points {
  const geometry = new THREE.BufferGeometry();
  const positions = observations.map(observationPosition);
  const colors = new Float32Array(positions.length * 3);
  const color = new THREE.Color();
  const ember = new THREE.Color("#c21607");
  const flame = new THREE.Color("#ff6a1a");
  const core = new THREE.Color("#ffd23f");
  const selectedColor = new THREE.Color("#fff6d8");

  observations.forEach((observation, index) => {
    const selected = observation.id === selectedObservationId;
    if (selected) {
      color.copy(selectedColor);
    } else {
      // FRP-scaled fire ramp: ember red -> flame orange -> hot yellow core.
      // Missing FRP renders as mid-flame orange, never as zero.
      const frp = typeof observation.frp === "number" && Number.isFinite(observation.frp) ? observation.frp : 12;
      const heat = Math.max(0, Math.min(1, Math.log10(1 + Math.max(0, frp)) / 2));
      if (heat < 0.5) color.copy(ember).lerp(flame, heat * 2);
      else color.copy(flame).lerp(core, (heat - 0.5) * 2);
    }
    colors[index * 3] = color.r;
    colors[index * 3 + 1] = color.g;
    colors[index * 3 + 2] = color.b;
  });

  geometry.setFromPoints(positions);
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  return new THREE.Points(
    geometry,
    new THREE.PointsMaterial({
      vertexColors: true,
      size: 0.1,
      sizeAttenuation: true,
      transparent: true,
      opacity: 0.95
    })
  );
}

function createAtmosphere(): THREE.Mesh {
  const material = new THREE.ShaderMaterial({
    transparent: true,
    side: THREE.BackSide,
    blending: THREE.AdditiveBlending,
    vertexShader: `
      varying vec3 vNormal;
      void main() {
        vNormal = normalize(normalMatrix * normal);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      varying vec3 vNormal;
      void main() {
        float intensity = pow(0.72 - dot(vNormal, vec3(0.0, 0.0, 1.0)), 2.4);
        gl_FragColor = vec4(0.20, 0.72, 0.92, intensity * 0.72);
      }
    `
  });
  return new THREE.Mesh(
    new THREE.SphereGeometry(EARTH_RADIUS * 1.12, 64, 32),
    material
  );
}

function createSatelliteModel(): { group: THREE.Group; dispose: () => void } {
  const group = new THREE.Group();
  group.name = "Earth-observing satellite";
  group.rotation.set(0.12, -0.18, 0.08);

  const geometries = new Set<THREE.BufferGeometry>();
  const materials = new Set<THREE.Material>();
  const material = (color: string, metalness: number, roughness: number) => {
    const value = new THREE.MeshStandardMaterial({ color, metalness, roughness, side: THREE.DoubleSide });
    materials.add(value);
    return value;
  };
  const foil = material("#c58b48", 0.78, 0.38);
  const foilLight = material("#e3bc7c", 0.7, 0.3);
  const structure = material("#9aaab5", 0.82, 0.27);
  const structureDark = material("#36434c", 0.86, 0.32);
  const panelBacking = material("#0d1b2e", 0.65, 0.32);
  const cellMaterials = [
    material("#183c66", 0.56, 0.31),
    material("#245383", 0.58, 0.28),
    material("#102b4d", 0.62, 0.3)
  ];
  const dishMaterial = material("#657987", 0.76, 0.26);
  const darkDishMaterial = material("#273642", 0.72, 0.3);
  const emissiveMaterial = new THREE.MeshStandardMaterial({
    color: "#e6d2aa", emissive: "#ff8a36", emissiveIntensity: 0.12,
    metalness: 0.7, roughness: 0.32
  });
  materials.add(emissiveMaterial);

  const addMesh = (geometry: THREE.BufferGeometry, surface: THREE.Material, name: string, position: THREE.Vector3) => {
    geometries.add(geometry);
    const mesh = new THREE.Mesh(geometry, surface);
    mesh.name = name;
    mesh.position.copy(position);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    group.add(mesh);
    return mesh;
  };
  const box = (name: string, size: [number, number, number], position: [number, number, number], surface: THREE.Material) =>
    addMesh(new THREE.BoxGeometry(...size), surface, name, new THREE.Vector3(...position));
  const cylinder = (
    name: string,
    radiusTop: number,
    radiusBottom: number,
    height: number,
    position: [number, number, number],
    surface: THREE.Material,
    radialSegments = 10
  ) => addMesh(new THREE.CylinderGeometry(radiusTop, radiusBottom, height, radialSegments), surface, name, new THREE.Vector3(...position));
  const strut = (name: string, from: THREE.Vector3, to: THREE.Vector3, radius: number, surface: THREE.Material) => {
    const direction = to.clone().sub(from);
    const mesh = addMesh(
      new THREE.CylinderGeometry(radius * 0.82, radius, direction.length(), 8),
      surface,
      name,
      from.clone().add(to).multiplyScalar(0.5)
    );
    mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.normalize());
    return mesh;
  };

  // The equipment bus uses layered foil, radiators, and exposed structural rails.
  box("bus frame", [0.43, 0.48, 0.39], [0, 0, 0], structureDark);
  box("gold thermal blanket front", [0.35, 0.37, 0.025], [0, 0.015, 0.207], foil);
  box("gold thermal blanket rear", [0.35, 0.37, 0.025], [0, 0.015, -0.207], foilLight);
  box("upper avionics panel", [0.27, 0.12, 0.025], [0, 0.155, 0.226], structure);
  box("lower radiator panel", [0.31, 0.14, 0.024], [0, -0.145, 0.225], structure);
  box("left equipment bay", [0.12, 0.29, 0.32], [-0.267, 0.02, 0], foilLight);
  box("right equipment bay", [0.12, 0.25, 0.3], [0.267, -0.015, 0], foil);
  box("front antenna deck", [0.25, 0.09, 0.035], [0, 0.275, 0.035], structure);
  box("rear radiator", [0.3, 0.31, 0.025], [0.015, 0.025, -0.23], structure);

  // Small instruments, rails, thrusters, and plumbing break up the bus silhouette.
  for (const x of [-0.16, 0.16]) {
    for (const z of [-0.13, 0.13]) {
      cylinder("bus corner standoff", 0.028, 0.028, 0.4, [x, 0, z], structure, 8);
    }
    box("bus side rail", [0.035, 0.52, 0.035], [x, 0, 0.018], foilLight);
  }
  for (const x of [-0.13, -0.045, 0.045, 0.13]) {
    box("radiator fin", [0.025, 0.2, 0.025], [x, -0.31, 0.08], structure);
  }
  cylinder("thruster body", 0.067, 0.09, 0.17, [0.02, -0.34, -0.04], structureDark, 12);
  cylinder("thruster nozzle", 0.09, 0.045, 0.1, [0.02, -0.46, -0.04], foilLight, 12);
  cylinder("side thruster left", 0.048, 0.07, 0.12, [-0.25, -0.2, -0.13], structure, 10).rotation.z = Math.PI / 2;
  cylinder("side thruster right", 0.048, 0.07, 0.12, [0.25, -0.2, -0.13], structure, 10).rotation.z = -Math.PI / 2;
  box("sensor housing", [0.13, 0.11, 0.16], [0.08, -0.06, 0.235], structureDark);
  cylinder("sensor barrel", 0.039, 0.054, 0.14, [0.08, -0.06, 0.36], structure, 12).rotation.x = Math.PI / 2;
  cylinder("sensor aperture", 0.033, 0.033, 0.012, [0.08, -0.06, 0.437], emissiveMaterial, 12).rotation.x = Math.PI / 2;

  // Solar wings: individual blue cells, reflective rails, and deployment booms.
  for (const side of [-1, 1]) {
    const wing = new THREE.Group();
    wing.name = side < 0 ? "port solar wing" : "starboard solar wing";
    group.add(wing);
    const wingPosition = new THREE.Vector3(side * 0.82, 0, 0.015);
    const backing = new THREE.Mesh(new THREE.BoxGeometry(1.18, 0.53, 0.018), panelBacking);
    backing.name = "solar wing backing";
    backing.position.copy(wingPosition);
    wing.add(backing);
    geometries.add(backing.geometry);

    for (let column = 0; column < 4; column += 1) {
      for (let row = 0; row < 3; row += 1) {
        const x = side * (0.37 + column * 0.278);
        const y = (row - 1) * 0.166;
        const cell = new THREE.Mesh(
          new THREE.BoxGeometry(0.248, 0.145, 0.009),
          cellMaterials[(column + row + (side > 0 ? 1 : 0)) % cellMaterials.length]
        );
        cell.name = "segmented photovoltaic cell";
        cell.position.set(x, y, 0.032);
        wing.add(cell);
        geometries.add(cell.geometry);
      }
    }
    const rootX = side * 0.23;
    const outerX = side * 1.41;
    for (const y of [-0.275, 0.275]) {
      const rail = new THREE.Mesh(new THREE.BoxGeometry(1.2, 0.018, 0.028), structure);
      rail.name = "solar array edge rail";
      rail.position.set(side * 0.82, y, 0.03);
      wing.add(rail);
      geometries.add(rail.geometry);
    }
    for (const x of [rootX, outerX]) {
      const rail = new THREE.Mesh(new THREE.BoxGeometry(0.018, 0.55, 0.028), foilLight);
      rail.name = "solar array end rail";
      rail.position.set(x, 0, 0.03);
      wing.add(rail);
      geometries.add(rail.geometry);
    }
    for (let column = 1; column < 4; column += 1) {
      const seam = new THREE.Mesh(new THREE.BoxGeometry(0.012, 0.51, 0.018), structureDark);
      seam.name = "solar cell divider";
      seam.position.set(side * (0.37 + column * 0.278 - 0.139), 0, 0.038);
      wing.add(seam);
      geometries.add(seam.geometry);
    }
    strut("solar wing deployment boom", new THREE.Vector3(side * 0.2, 0.04, 0.01), new THREE.Vector3(side * 0.33, 0.02, 0.02), 0.022, foilLight);
    strut("wing support brace", new THREE.Vector3(side * 0.22, -0.18, -0.015), new THREE.Vector3(side * 0.4, 0.18, -0.015), 0.012, structure);
  }

  // Concave reflectors, feed horns, and booms give the craft its communications payload silhouette.
  const addDish = (name: string, position: [number, number, number], radius: number, surface: THREE.Material) => {
    const dishGroup = new THREE.Group();
    dishGroup.name = name;
    dishGroup.position.set(...position);
    group.add(dishGroup);
    const profile = [
      new THREE.Vector2(0, 0.012),
      new THREE.Vector2(radius * 0.27, 0.02),
      new THREE.Vector2(radius * 0.53, radius * 0.12),
      new THREE.Vector2(radius * 0.78, radius * 0.29),
      new THREE.Vector2(radius, radius * 0.5)
    ];
    const reflector = new THREE.Mesh(new THREE.LatheGeometry(profile, 28), surface);
    reflector.name = "parabolic antenna reflector";
    reflector.rotation.x = Math.PI / 2;
    dishGroup.add(reflector);
    geometries.add(reflector.geometry);
    const rim = new THREE.Mesh(new THREE.TorusGeometry(radius, 0.012, 6, 32), structure);
    rim.name = "antenna rim";
    rim.position.z = radius * 0.5;
    dishGroup.add(rim);
    geometries.add(rim.geometry);
    const feedArm = new THREE.Mesh(new THREE.CylinderGeometry(0.008, 0.008, radius * 0.84, 6), foilLight);
    feedArm.name = "antenna feed support";
    feedArm.rotation.x = Math.PI / 2;
    feedArm.position.set(0, 0, radius * 0.29);
    dishGroup.add(feedArm);
    geometries.add(feedArm.geometry);
    const feed = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.022, 0.075, 8), structureDark);
    feed.name = "antenna feed horn";
    feed.rotation.x = Math.PI / 2;
    feed.position.set(0, 0, radius * 0.55 + 0.035);
    dishGroup.add(feed);
    geometries.add(feed.geometry);
    strut("antenna mounting boom", new THREE.Vector3(position[0] * 0.6, position[1] * 0.55, 0.08), new THREE.Vector3(position[0], position[1], position[2]), 0.014, structure);
  };
  addDish("large high-gain dish", [-0.22, 0.31, 0.2], 0.19, darkDishMaterial);
  addDish("secondary high-gain dish", [0.29, -0.22, 0.18], 0.145, dishMaterial);
  addDish("small telemetry dish", [-0.22, -0.28, 0.13], 0.09, structure);

  strut("top antenna mast", new THREE.Vector3(0.13, 0.23, -0.08), new THREE.Vector3(0.22, 0.49, -0.08), 0.009, structure);
  strut("antenna crossbar", new THREE.Vector3(0.16, 0.42, -0.08), new THREE.Vector3(0.29, 0.42, -0.08), 0.007, foilLight);
  const beacon = new THREE.PointLight("#b4dcff", 0.24, 1.1, 2);
  beacon.position.set(0.02, 0.12, 0.27);
  group.add(beacon);

  return {
    group,
    dispose: () => {
      geometries.forEach((geometry) => geometry.dispose());
      materials.forEach((surface) => surface.dispose());
    }
  };
}

export function ThreeGlobeView({
  containerRef,
  observations,
  selectedObservationId,
  onSelectObservation,
  onMapClick,
  zoomRequest,
  resetRequestId,
  flyTo,
  onReady
}: GlobeViewProps) {
  const sceneRef = useRef<THREE.Scene | null>(null);
  const globeGroupRef = useRef<THREE.Group | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const pointsRef = useRef<THREE.Points | null>(null);
  const observationIdsRef = useRef<string[]>([]);
  const lastZoomRequestRef = useRef(0);
  const lastResetRequestRef = useRef(0);
  const lastFlyToRequestRef = useRef(0);
  const onReadyRef = useRef(onReady);
  onReadyRef.current = onReady;
  const onMapClickRef = useRef(onMapClick);
  onMapClickRef.current = onMapClick;
  const readyFiredRef = useRef(false);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#030609");
    sceneRef.current = scene;

    const camera = new THREE.PerspectiveCamera(36, 1, 0.1, 100);
    camera.position.set(0, 0.15, 5.2);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, MAX_DPR));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    container.replaceChildren(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.07;
    controls.enablePan = true;
    controls.minDistance = 2.2;
    controls.maxDistance = 7;
    controls.target.set(0, 0, 0);
    controlsRef.current = controls;

    const backdrop = createMilkyWayBackdrop();
    scene.add(backdrop);
    const stars = createStarfield();
    scene.add(stars);

    scene.add(new THREE.AmbientLight(0x333333, 1));
    const sun = new THREE.DirectionalLight("#FFF1D5", 3.1);
    sun.position.set(5, 3, 5);
    scene.add(sun);
    const flare = createLensFlare(sun.position.clone().normalize().multiplyScalar(EARTH_RADIUS * 1.28));
    scene.add(flare);

    const globeGroup = new THREE.Group();
    const centerLatitude = THREE.MathUtils.degToRad(5);
    const centerLongitude = THREE.MathUtils.degToRad(20);
    const centerDirection = new THREE.Vector3(
      Math.cos(centerLatitude) * Math.sin(centerLongitude),
      Math.sin(centerLatitude),
      Math.cos(centerLatitude) * Math.cos(centerLongitude)
    );
    globeGroup.quaternion.setFromUnitVectors(centerDirection, new THREE.Vector3(0, 0, 1));
    scene.add(globeGroup);
    globeGroupRef.current = globeGroup;

    const loader = new THREE.TextureLoader();
    let isDisposed = false;
    const blackPixel = new THREE.DataTexture(new Uint8Array([0, 0, 0, 255]), 1, 1);
    blackPixel.needsUpdate = true;
    const earthUniforms = {
      dayMap: { value: createEarthFallbackTexture() as THREE.Texture },
      nightMap: { value: blackPixel as THREE.Texture },
      sunDirection: { value: new THREE.Vector3(5, 3, 5).normalize() },
      uvOffset: { value: 0.25 }
    };
    const earthMaterial = new THREE.ShaderMaterial({
      uniforms: earthUniforms,
      vertexShader: /* glsl */ `
        varying vec2 vUv;
        varying vec3 vNormal;
        void main() {
          vUv = uv;
          vNormal = normalize(normalMatrix * normal);
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: /* glsl */ `
        uniform sampler2D dayMap;
        uniform sampler2D nightMap;
        uniform vec3 sunDirection;
        uniform float uvOffset;
        varying vec2 vUv;
        varying vec3 vNormal;
        void main() {
          vec2 uv = vec2(fract(vUv.x + uvOffset), vUv.y);
          float ndl = dot(normalize(vNormal), normalize(sunDirection));
          float dayMix = smoothstep(-0.12, 0.28, ndl);
          vec3 dayCol = texture2D(dayMap, uv).rgb;
          vec3 nightCol = texture2D(nightMap, uv).rgb;
          vec3 nightBase = dayCol * 0.02 + vec3(0.002, 0.004, 0.01);
          vec3 col = mix(nightBase + nightCol * 2.0, dayCol, dayMix);
          gl_FragColor = vec4(col, 1.0);
        }
      `
    });
    earthMaterial.toneMapped = false;
    const fallbackTexture = earthUniforms.dayMap.value;
    const maxTextureSize = renderer.capabilities.maxTextureSize;
    const earthTextureUrl = maxTextureSize >= 8192 ? EARTH_TEXTURE_8K_URL : EARTH_TEXTURE_4K_URL;
    const earthTexture = loader.load(earthTextureUrl, (texture) => {
      if (isDisposed) {
        texture.dispose();
        return;
      }
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.wrapS = THREE.RepeatWrapping;
      texture.anisotropy = renderer.capabilities.getMaxAnisotropy();
      earthUniforms.dayMap.value = texture;
      fallbackTexture?.dispose();
    });
    let nightLightsTexture: THREE.Texture | null = null;
    const nightTexture = loader.load(
      NIGHT_TEXTURE_4K_URL,
      (texture) => {
        if (isDisposed) {
          texture.dispose();
          return;
        }
        texture.colorSpace = THREE.SRGBColorSpace;
        texture.wrapS = THREE.RepeatWrapping;
        try {
          nightLightsTexture = extractCityLightsTexture(texture.image as HTMLImageElement);
          nightLightsTexture.anisotropy = Math.min(4, renderer.capabilities.getMaxAnisotropy());
          earthUniforms.nightMap.value = nightLightsTexture;
          texture.dispose();
        } catch {
          // Fall back to the raw night map rather than losing the night side.
          earthUniforms.nightMap.value = texture;
        }
        blackPixel.dispose();
      },
      undefined,
      () => {
        // Night texture missing: the terminator still darkens the day side.
      }
    );
    const earth = new THREE.Mesh(
      new THREE.SphereGeometry(EARTH_RADIUS, 96, 64),
      earthMaterial
    );
    globeGroup.add(earth);

    const cloudMaterial = new THREE.MeshPhongMaterial({
      color: "#f6f7fb",
      transparent: true,
      opacity: 0.9,
      depthWrite: false,
      shininess: 4,
      side: THREE.FrontSide
    });
    const cloudTextureUrl = CLOUD_TEXTURE_4K_URL;
    const cloudTexture = loader.load(cloudTextureUrl, (texture) => {
      if (isDisposed) {
        texture.dispose();
        return;
      }
      texture.colorSpace = THREE.NoColorSpace;
      texture.wrapS = THREE.RepeatWrapping;
      texture.offset.x = 0.25;
      texture.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
      cloudMaterial.alphaMap = texture;
      cloudMaterial.needsUpdate = true;
    });
    cloudMaterial.alphaMap = cloudTexture;
    const clouds = new THREE.Mesh(
      new THREE.SphereGeometry(EARTH_RADIUS * 1.012, 64, 48),
      cloudMaterial
    );
    globeGroup.add(clouds);
    const atmosphere = createAtmosphere();
    globeGroup.add(atmosphere);

    const orbitObject = new THREE.Object3D();
    const satelliteModel = createSatelliteModel();
    const satelliteGroup = satelliteModel.group;
    satelliteGroup.scale.setScalar(0.26);

    const satelliteTrailGeometry = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(0, 0, 0.07),
      new THREE.Vector3(0, 0, 0.22),
      new THREE.Vector3(0, 0, 0.38),
      new THREE.Vector3(0, 0, 0.56)
    ]);
    const satelliteTrail = new THREE.Line(
      satelliteTrailGeometry,
      new THREE.LineBasicMaterial({
        color: "#8bdcff",
        transparent: true,
        opacity: 0.42,
        depthWrite: false
      })
    );
    satelliteTrail.scale.setScalar(1 / 0.26);
    satelliteGroup.add(satelliteTrail);

    satelliteGroup.position.set(EARTH_RADIUS + 0.4, 0, 0);
    orbitObject.add(satelliteGroup);
    scene.add(orbitObject);

    const resize = () => {
      const { width, height } = container.getBoundingClientRect();
      camera.aspect = Math.max(width, 1) / Math.max(height, 1);
      camera.updateProjectionMatrix();
      renderer.setSize(Math.max(width, 1), Math.max(height, 1), false);
    };
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(container);
    resize();

    const raycaster = new THREE.Raycaster();
    raycaster.params.Points.threshold = 0.13;
    const pointer = new THREE.Vector2();
    let pointerDown: { x: number; y: number } | null = null;
    const onPointerDown = (event: PointerEvent) => {
      pointerDown = { x: event.clientX, y: event.clientY };
    };
    const onPointerUp = (event: PointerEvent) => {
      if (!pointerDown || Math.hypot(event.clientX - pointerDown.x, event.clientY - pointerDown.y) > 5) {
        pointerDown = null;
        return;
      }
      const bounds = renderer.domElement.getBoundingClientRect();
      pointer.set(
        ((event.clientX - bounds.left) / bounds.width) * 2 - 1,
        -((event.clientY - bounds.top) / bounds.height) * 2 + 1
      );
      raycaster.setFromCamera(pointer, camera);
      const [hit] = raycaster.intersectObject(pointsRef.current ?? scene);
      onSelectObservation(
        hit?.index === undefined ? null : observationIdsRef.current[hit.index] ?? null
      );
      if (hit?.index === undefined && onMapClickRef.current) {
        // Empty globe click: report the surface lat/lon so the app can lock
        // it as the query center (inverse of observationPosition).
        const [surface] = raycaster.intersectObject(earth);
        if (surface) {
          const local = globeGroup.worldToLocal(surface.point.clone()).normalize();
          const lat = THREE.MathUtils.radToDeg(
            Math.asin(THREE.MathUtils.clamp(local.y, -1, 1))
          );
          const lon = THREE.MathUtils.radToDeg(Math.atan2(local.x, local.z));
          if (Number.isFinite(lat) && Number.isFinite(lon)) {
            onMapClickRef.current({ lat, lon });
          }
        }
      }
      pointerDown = null;
    };
    renderer.domElement.addEventListener("pointerdown", onPointerDown);
    renderer.domElement.addEventListener("pointerup", onPointerUp);

    let animationFrame = 0;
    const sunViewDirection = new THREE.Vector3();
    const render = () => {
      controls.update();
      clouds.rotation.y += 0.00015;
      orbitObject.rotation.y += 0.005;
      orbitObject.rotation.x += 0.001;
      sunViewDirection.copy(sun.position).transformDirection(camera.matrixWorldInverse);
      earthUniforms.sunDirection.value.copy(sunViewDirection);
      renderer.render(scene, camera);
      if (!readyFiredRef.current) {
        readyFiredRef.current = true;
        onReadyRef.current?.();
      }
      animationFrame = requestAnimationFrame(render);
    };
    render();

    return () => {
      isDisposed = true;
      cancelAnimationFrame(animationFrame);
      renderer.domElement.removeEventListener("pointerdown", onPointerDown);
      renderer.domElement.removeEventListener("pointerup", onPointerUp);
      resizeObserver.disconnect();
      controls.dispose();
      if (pointsRef.current) {
        globeGroup.remove(pointsRef.current);
        pointsRef.current.geometry.dispose();
        (pointsRef.current.material as THREE.PointsMaterial).dispose();
        pointsRef.current = null;
      }
      earth.geometry.dispose();
      earthTexture.dispose();
      nightTexture.dispose();
      nightLightsTexture?.dispose();
      blackPixel.dispose();
      (earthUniforms.dayMap.value as THREE.Texture)?.dispose?.();
      earthMaterial.dispose();
      clouds.geometry.dispose();
      cloudTexture.dispose();
      cloudMaterial.dispose();
      satelliteModel.dispose();
      satelliteTrailGeometry.dispose();
      satelliteTrail.material.dispose();
      orbitObject.remove(satelliteGroup);
      scene.remove(orbitObject);
      atmosphere.geometry.dispose();
      (atmosphere.material as THREE.Material).dispose();
      backdrop.geometry.dispose();
      (backdrop.material as THREE.MeshBasicMaterial).map?.dispose();
      (backdrop.material as THREE.Material).dispose();
      stars.geometry.dispose();
      (stars.material as THREE.Material).dispose();
      const flareTextures = new Set<THREE.Texture>();
      flare.traverse((object) => {
        if (object instanceof THREE.Sprite) {
          const material = object.material as THREE.SpriteMaterial;
          if (material.map) flareTextures.add(material.map);
          material.dispose();
        }
      });
      flareTextures.forEach((texture) => texture.dispose());
      globeGroup.clear();
      scene.remove(globeGroup);
      renderer.dispose();
      container.replaceChildren();
      sceneRef.current = null;
      globeGroupRef.current = null;
      cameraRef.current = null;
      controlsRef.current = null;
    };
  }, [containerRef, onSelectObservation]);

  useEffect(() => {
    const scene = sceneRef.current;
    const globeGroup = globeGroupRef.current;
    if (!scene || !globeGroup) return;
    if (pointsRef.current) {
      globeGroup.remove(pointsRef.current);
      pointsRef.current.geometry.dispose();
      (pointsRef.current.material as THREE.PointsMaterial).dispose();
    }

    const limitedObservations = observations.slice(0, 2000);
    pointsRef.current = createObservationPoints(limitedObservations, selectedObservationId);
    observationIdsRef.current = limitedObservations.map(({ id }) => id);
    globeGroup.add(pointsRef.current);
  }, [observations, selectedObservationId]);

  useEffect(() => {
    const controls = controlsRef.current;
    if (!controls || !zoomRequest || zoomRequest.requestId === lastZoomRequestRef.current) return;
    const distance = controls.object.position.distanceTo(controls.target);
    const multiplier = zoomRequest.direction === "in" ? 0.78 : 1.28;
    controls.object.position.setLength(THREE.MathUtils.clamp(distance * multiplier, 2.2, 7));
    controls.update();
    lastZoomRequestRef.current = zoomRequest.requestId;
  }, [zoomRequest]);

  useEffect(() => {
    const controls = controlsRef.current;
    if (!controls || resetRequestId === undefined || resetRequestId === lastResetRequestRef.current) return;
    controls.object.position.set(0, 0.15, 5.2);
    controls.target.set(0, 0, 0);
    controls.update();
    lastResetRequestRef.current = resetRequestId;
  }, [resetRequestId]);

  useEffect(() => {
    const globeGroup = globeGroupRef.current;
    const controls = controlsRef.current;
    if (!globeGroup || !controls || !flyTo || flyTo.requestId === lastFlyToRequestRef.current) return;
    const lat = THREE.MathUtils.degToRad(Math.max(-90, Math.min(90, flyTo.lat)));
    const lon = THREE.MathUtils.degToRad(((flyTo.lon + 540) % 360) - 180);
    const direction = new THREE.Vector3(
      Math.cos(lat) * Math.sin(lon),
      Math.sin(lat),
      Math.cos(lat) * Math.cos(lon)
    );
    globeGroup.quaternion.setFromUnitVectors(direction, new THREE.Vector3(0, 0, 1));
    controls.object.position.setLength(THREE.MathUtils.clamp(3.1, controls.minDistance, controls.maxDistance));
    controls.update();
    lastFlyToRequestRef.current = flyTo.requestId;
  }, [flyTo]);

  return null;
}
