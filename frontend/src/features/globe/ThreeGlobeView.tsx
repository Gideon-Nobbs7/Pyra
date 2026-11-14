import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import type { GlobeObservation, GlobeViewProps } from "./GlobeView";

const EARTH_RADIUS = 1.65;
const MAX_DPR = 1.5;
const EARTH_TEXTURE_8K_URL = `${import.meta.env.BASE_URL}textures/earth-day-8192.webp`;
const EARTH_TEXTURE_4K_URL = `${import.meta.env.BASE_URL}textures/earth-day-4096.webp`;
const BUMP_TEXTURE_URL = `${import.meta.env.BASE_URL}textures/earth-bump-2048.webp`;
const CLOUD_TEXTURE_4K_URL = `${import.meta.env.BASE_URL}textures/earth-clouds-alpha-4096.webp`;

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

  observations.forEach((observation, index) => {
    const selected = observation.id === selectedObservationId;
    color.set(selected ? "#ffd2a8" : observation.source === "modis" ? "#4fd1a5" : "#f4a261");
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

export function ThreeGlobeView({
  containerRef,
  observations,
  selectedObservationId,
  onSelectObservation,
  zoomRequest,
  resetRequestId
}: GlobeViewProps) {
  const sceneRef = useRef<THREE.Scene | null>(null);
  const globeGroupRef = useRef<THREE.Group | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const pointsRef = useRef<THREE.Points | null>(null);
  const observationIdsRef = useRef<string[]>([]);
  const lastZoomRequestRef = useRef(0);
  const lastResetRequestRef = useRef(0);

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

    scene.add(new THREE.AmbientLight("#42677A", 0.56));
    const sun = new THREE.DirectionalLight("#FFF1D5", 3.1);
    sun.position.set(-4, 2.5, 5);
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
    const earthMaterial = new THREE.MeshPhongMaterial({
      map: createEarthFallbackTexture(),
      shininess: 9,
      specular: new THREE.Color("#6ca9c6")
    });
    const fallbackTexture = earthMaterial.map;
    const maxTextureSize = renderer.capabilities.maxTextureSize;
    const earthTextureUrl = maxTextureSize >= 8192 ? EARTH_TEXTURE_8K_URL : EARTH_TEXTURE_4K_URL;
    const earthTexture = loader.load(earthTextureUrl, (texture) => {
      if (isDisposed) {
        texture.dispose();
        return;
      }
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.wrapS = THREE.RepeatWrapping;
      texture.offset.x = 0.25;
      texture.anisotropy = renderer.capabilities.getMaxAnisotropy();
      earthMaterial.map = texture;
      earthMaterial.needsUpdate = true;
      fallbackTexture?.dispose();
    });
    const bumpTexture = loader.load(BUMP_TEXTURE_URL, (texture) => {
      if (isDisposed) {
        texture.dispose();
        return;
      }
      texture.colorSpace = THREE.NoColorSpace;
      texture.wrapS = THREE.RepeatWrapping;
      texture.offset.x = 0.25;
      texture.anisotropy = Math.min(4, renderer.capabilities.getMaxAnisotropy());
      earthMaterial.bumpMap = texture;
      earthMaterial.bumpScale = 0.045;
      earthMaterial.needsUpdate = true;
    });
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
      pointerDown = null;
    };
    renderer.domElement.addEventListener("pointerdown", onPointerDown);
    renderer.domElement.addEventListener("pointerup", onPointerUp);

    let animationFrame = 0;
    const render = () => {
      controls.update();
      clouds.rotation.y += 0.00015;
      renderer.render(scene, camera);
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
      bumpTexture.dispose();
      earthMaterial.map?.dispose();
      earthMaterial.dispose();
      clouds.geometry.dispose();
      cloudTexture.dispose();
      cloudMaterial.dispose();
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

  return null;
}
