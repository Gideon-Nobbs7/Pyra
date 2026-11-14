import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import type { GlobeObservation, GlobeViewProps } from "./GlobeView";

const EARTH_RADIUS = 1.65;
const MAX_DPR = 1.5;

function createEarthTexture(): THREE.CanvasTexture {
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

function createCloudTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 256;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Unable to create the procedural cloud texture.");

  for (let index = 0; index < 70; index += 1) {
    const x = (index * 83) % canvas.width;
    const y = 24 + ((index * 47) % 190);
    context.fillStyle = `rgba(255, 255, 255, ${0.08 + (index % 4) * 0.025})`;
    context.beginPath();
    context.ellipse(
      x,
      y,
      24 + (index % 6) * 13,
      7 + (index % 4) * 4,
      index * 0.2,
      0,
      Math.PI * 2
    );
    context.fill();
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

function createStarfield(): THREE.Points {
  const positions = new Float32Array(450 * 3);
  for (let index = 0; index < 450; index += 1) {
    const radius = 8 + (index % 6) * 1.5;
    const theta = (index * 2.399963) % (Math.PI * 2);
    const phi = Math.acos(1 - 2 * ((index + 1) / 451));
    positions[index * 3] = radius * Math.sin(phi) * Math.cos(theta);
    positions[index * 3 + 1] = radius * Math.cos(phi);
    positions[index * 3 + 2] = radius * Math.sin(phi) * Math.sin(theta);
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  return new THREE.Points(
    geometry,
    new THREE.PointsMaterial({
      color: "#b9d9e7",
      size: 0.025,
      sizeAttenuation: true,
      transparent: true,
      opacity: 0.72
    })
  );
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

    scene.add(new THREE.AmbientLight("#42677A", 0.9));
    const sun = new THREE.DirectionalLight("#FFF4DC", 2.6);
    sun.position.set(-4, 2.5, 5);
    scene.add(sun);
    scene.add(createStarfield());

    const earthMaterial = new THREE.MeshPhongMaterial({
      map: createEarthTexture(),
      shininess: 12,
      specular: new THREE.Color("#7fcfe3")
    });
    const earth = new THREE.Mesh(
      new THREE.SphereGeometry(EARTH_RADIUS, 96, 64),
      earthMaterial
    );
    scene.add(earth);

    const cloudMaterial = new THREE.MeshPhongMaterial({
      alphaMap: createCloudTexture(),
      color: "#ffffff",
      transparent: true,
      opacity: 0.42,
      depthWrite: false
    });
    const clouds = new THREE.Mesh(
      new THREE.SphereGeometry(EARTH_RADIUS * 1.012, 64, 48),
      cloudMaterial
    );
    scene.add(clouds);
    scene.add(createAtmosphere());

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
      cancelAnimationFrame(animationFrame);
      renderer.domElement.removeEventListener("pointerdown", onPointerDown);
      renderer.domElement.removeEventListener("pointerup", onPointerUp);
      resizeObserver.disconnect();
      controls.dispose();
      earth.geometry.dispose();
      earthMaterial.map?.dispose();
      earthMaterial.dispose();
      clouds.geometry.dispose();
      cloudMaterial.alphaMap?.dispose();
      cloudMaterial.dispose();
      renderer.dispose();
      container.replaceChildren();
      sceneRef.current = null;
      cameraRef.current = null;
      controlsRef.current = null;
    };
  }, [containerRef, onSelectObservation]);

  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;
    if (pointsRef.current) {
      scene.remove(pointsRef.current);
      pointsRef.current.geometry.dispose();
      (pointsRef.current.material as THREE.PointsMaterial).dispose();
    }

    const limitedObservations = observations.slice(0, 2000);
    pointsRef.current = createObservationPoints(limitedObservations, selectedObservationId);
    observationIdsRef.current = limitedObservations.map(({ id }) => id);
    scene.add(pointsRef.current);
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
