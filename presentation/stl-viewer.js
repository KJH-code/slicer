/* global THREE */

/**
 * STL 메시를 표시하고 선택적인 components.json을 이용해
 * 삼각형별 연결 성분 색상을 적용하는 경량 Three.js 뷰어.
 */
class ResearchSTLViewer {
  constructor(container, options = {}) {
    this.container = container;
    this.canvasHost = container?.querySelector(".stl-canvas");
    this.placeholder = container?.querySelector(".viewer-placeholder");
    this.status = container?.querySelector(".viewer-status");
    this.legend = options.legend || null;
    this.scene = null;
    this.camera = null;
    this.renderer = null;
    this.controls = null;
    this.modelGroup = null;
    this.resizeObserver = null;
    this.frameId = null;
    this.active = false;
    this.initialized = false;
    this.options = options;
    this.palette = ["#ff9d45", "#2de2c5", "#63b3ff", "#b99cff", "#56d88a", "#ff7b72"];
  }

  initialize() {
    if (this.initialized || !this.container || !this.canvasHost) return;
    this.initialized = true;

    if (typeof window.THREE === "undefined" || typeof THREE.STLLoader === "undefined") {
      this.setMessage("Three.js 또는 STLLoader를 불러오지 못했습니다.");
      return;
    }

    try {
      this.scene = new THREE.Scene();
      this.scene.background = new THREE.Color(0x07111d);

      this.camera = new THREE.PerspectiveCamera(42, 1, 0.01, 100000);
      this.camera.up.set(0, 0, 1);

      this.renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: false,
        powerPreference: "low-power"
      });
      this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
      this.renderer.outputEncoding = THREE.sRGBEncoding;
      this.canvasHost.appendChild(this.renderer.domElement);

      if (typeof THREE.OrbitControls === "function") {
        this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.075;
        this.controls.screenSpacePanning = true;
      }

      const ambient = new THREE.HemisphereLight(0xcbeeff, 0x142132, 1.15);
      const key = new THREE.DirectionalLight(0xffffff, 1.1);
      const rim = new THREE.DirectionalLight(0x2de2c5, 0.65);
      key.position.set(4, -5, 8);
      rim.position.set(-5, 4, 5);
      this.scene.add(ambient, key, rim);

      const grid = new THREE.GridHelper(220, 22, 0x2de2c5, 0x29435a);
      grid.rotation.x = Math.PI / 2;
      grid.material.opacity = 0.3;
      grid.material.transparent = true;
      this.scene.add(grid);

      const axes = new THREE.AxesHelper(28);
      this.scene.add(axes);

      this.resizeObserver = new ResizeObserver(() => this.resize());
      this.resizeObserver.observe(this.container);
      this.renderer.domElement.addEventListener("wheel", (event) => event.stopPropagation(), {
        passive: true
      });

      this.resetCamera();
      this.resize();
      this.renderOnce();
    } catch (error) {
      this.setMessage("이 브라우저에서는 WebGL 3D 뷰어를 실행할 수 없습니다.");
      this.disposeRenderer();
    }
  }

  setActive(active) {
    this.active = Boolean(active);
    if (this.active) {
      this.resize();
      this.startLoop();
    } else {
      this.stopLoop();
    }
  }

  startLoop() {
    if (!this.renderer || this.frameId !== null) return;
    const tick = () => {
      if (!this.active || !this.renderer) {
        this.frameId = null;
        return;
      }
      this.controls?.update();
      this.renderer.render(this.scene, this.camera);
      this.frameId = window.requestAnimationFrame(tick);
    };
    this.frameId = window.requestAnimationFrame(tick);
  }

  stopLoop() {
    if (this.frameId !== null) {
      window.cancelAnimationFrame(this.frameId);
      this.frameId = null;
    }
  }

  renderOnce() {
    if (!this.renderer || !this.scene || !this.camera) return;
    this.controls?.update();
    this.renderer.render(this.scene, this.camera);
  }

  resize() {
    if (!this.renderer || !this.camera) return;
    const width = Math.max(1, this.container.clientWidth || 640);
    const height = Math.max(1, this.container.clientHeight || 420);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height, false);
    this.renderOnce();
  }

  async loadFromFiles(stlFile, componentFile = null) {
    if (!stlFile) {
      this.setMessage("STL 파일을 선택하세요.");
      return false;
    }

    try {
      const [stlBuffer, componentData] = await Promise.all([
        stlFile.arrayBuffer(),
        componentFile ? componentFile.text().then((text) => JSON.parse(text)) : Promise.resolve(null)
      ]);
      this.loadArrayBuffer(stlBuffer, componentData, stlFile.name);
      return true;
    } catch (error) {
      this.showPlaceholder("선택한 STL 또는 JSON 파일을 읽을 수 없습니다.");
      return false;
    }
  }

  async loadFromUrls(stlUrl, componentUrl = null) {
    if (window.location.protocol === "file:") {
      this.showPlaceholder("폴더 자동 로드는 로컬 HTTP 서버에서 사용할 수 있습니다.");
      return false;
    }

    this.setMessage("파일을 불러오는 중...");
    try {
      const stlResponse = await fetch(stlUrl, { cache: "no-store" });
      if (!stlResponse.ok) throw new Error("stl-not-found");

      let componentData = null;
      if (componentUrl) {
        const componentResponse = await fetch(componentUrl, { cache: "no-store" });
        if (!componentResponse.ok) throw new Error("component-not-found");
        componentData = await componentResponse.json();
      }

      const stlBuffer = await stlResponse.arrayBuffer();
      const displayName = stlUrl.split("/").pop() || "STL";
      this.loadArrayBuffer(stlBuffer, componentData, displayName);
      return true;
    } catch (error) {
      this.showPlaceholder("예정된 경로에 STL 또는 JSON 파일이 없습니다.");
      return false;
    }
  }

  loadArrayBuffer(stlBuffer, componentData, displayName) {
    if (!this.renderer) {
      this.initialize();
      if (!this.renderer) return;
    }

    const loader = new THREE.STLLoader();
    const parsed = loader.parse(stlBuffer);
    const geometry = parsed.index ? parsed.toNonIndexed() : parsed;
    const colored = this.applyColors(geometry, componentData);
    this.normalizeGeometry(colored);
    this.replaceModel(colored);
    this.renderLegend(componentData);
    this.container.classList.add("has-model");
    this.setMessage(`${displayName} · 면 ${Math.floor(colored.attributes.position.count / 3).toLocaleString()}개`);
  }

  applyColors(geometry, componentData) {
    const position = geometry.getAttribute("position");
    const triangleCount = Math.floor(position.count / 3);
    const faceComponents = componentData?.faceComponents;

    if (faceComponents && faceComponents.length !== triangleCount) {
      throw new Error("component-face-count-mismatch");
    }

    const baseColor = new THREE.Color("#73879a");
    const components = Array.isArray(componentData?.components) ? componentData.components : [];
    const componentColors = components.map((component, index) =>
      new THREE.Color(component.color || this.palette[index % this.palette.length])
    );

    const colors = new Float32Array(position.count * 3);
    const colorAttribute = new THREE.BufferAttribute(colors, 3);

    for (let faceIndex = 0; faceIndex < triangleCount; faceIndex += 1) {
      const componentIndex = faceComponents ? Number(faceComponents[faceIndex]) : -1;
      const color = componentIndex >= 0 && componentColors[componentIndex]
        ? componentColors[componentIndex]
        : baseColor;

      for (let offset = 0; offset < 3; offset += 1) {
        const vertexIndex = faceIndex * 3 + offset;
        colorAttribute.setXYZ(vertexIndex, color.r, color.g, color.b);
      }
    }

    geometry.setAttribute("color", colorAttribute);
    geometry.computeVertexNormals();
    return geometry;
  }

  normalizeGeometry(geometry) {
    geometry.computeBoundingBox();
    const box = geometry.boundingBox;
    const center = new THREE.Vector3();
    box.getCenter(center);
    geometry.translate(-center.x, -center.y, -box.min.z);
    geometry.computeBoundingBox();
    geometry.computeBoundingSphere();
  }

  replaceModel(geometry) {
    this.disposeModel();

    const material = new THREE.MeshStandardMaterial({
      vertexColors: true,
      flatShading: true,
      side: THREE.DoubleSide,
      roughness: 0.72,
      metalness: 0.04
    });

    const mesh = new THREE.Mesh(geometry, material);
    const edgeGeometry = new THREE.EdgesGeometry(geometry, 28);
    const edgeMaterial = new THREE.LineBasicMaterial({
      color: 0xd6edf8,
      transparent: true,
      opacity: 0.16
    });
    const edges = new THREE.LineSegments(edgeGeometry, edgeMaterial);

    this.modelGroup = new THREE.Group();
    this.modelGroup.add(mesh, edges);
    this.scene.add(this.modelGroup);
    this.fitCamera(geometry);
    this.renderOnce();
  }

  fitCamera(geometry) {
    geometry.computeBoundingBox();
    const box = geometry.boundingBox;
    const size = new THREE.Vector3();
    box.getSize(size);
    const maxDimension = Math.max(size.x, size.y, size.z, 1);
    const distance = maxDimension * 2.15;
    const targetZ = size.z * 0.46;

    this.camera.near = Math.max(maxDimension / 1000, 0.01);
    this.camera.far = maxDimension * 40;
    this.camera.position.set(distance * 0.95, -distance * 1.05, distance * 0.78);
    this.camera.updateProjectionMatrix();

    if (this.controls) {
      this.controls.target.set(0, 0, targetZ);
      this.controls.update();
    } else {
      this.camera.lookAt(0, 0, targetZ);
    }
  }

  resetCamera() {
    if (this.modelGroup) {
      const mesh = this.modelGroup.children.find((child) => child.isMesh);
      if (mesh) {
        this.fitCamera(mesh.geometry);
        return;
      }
    }
    this.camera?.position.set(150, -170, 120);
    this.controls?.target.set(0, 0, 35);
    this.controls?.update();
    this.renderOnce();
  }

  renderLegend(componentData) {
    if (!this.legend) return;
    this.legend.replaceChildren();

    const base = document.createElement("span");
    const baseSwatch = document.createElement("i");
    baseSwatch.style.setProperty("--legend", "#73879a");
    base.append(baseSwatch, document.createTextNode("일반 면"));
    this.legend.appendChild(base);

    const components = Array.isArray(componentData?.components) ? componentData.components : [];
    if (!components.length) {
      const placeholder = document.createElement("span");
      placeholder.className = "legend-placeholder";
      placeholder.textContent = "연결 성분 JSON이 없어 일반 색상으로 표시";
      this.legend.appendChild(placeholder);
      return;
    }

    components.forEach((component, index) => {
      const item = document.createElement("span");
      const color = component.color || this.palette[index % this.palette.length];
      const label = component.label || `I_c${index + 1}`;
      const angle = Number.isFinite(Number(component.selectedAngleDeg))
        ? ` · α=${Number(component.selectedAngleDeg)}°`
        : "";
      const swatch = document.createElement("i");
      swatch.style.setProperty("--legend", color);
      item.append(swatch, document.createTextNode(`${label}${angle}`));
      this.legend.appendChild(item);
    });
  }

  showPlaceholder(message, expectedName = null) {
    this.disposeModel();
    this.container.classList.remove("has-model");
    if (this.placeholder) {
      const strong = this.placeholder.querySelector("strong");
      const span = this.placeholder.querySelector("span");
      if (expectedName && strong) strong.textContent = expectedName;
      if (span) span.textContent = message;
    }
    this.setMessage(message);
    this.renderLegend(null);
  }

  setMessage(message) {
    if (this.status) this.status.textContent = message;
  }

  disposeModel() {
    if (!this.modelGroup || !this.scene) return;
    this.scene.remove(this.modelGroup);
    this.modelGroup.traverse((object) => {
      object.geometry?.dispose?.();
      if (Array.isArray(object.material)) object.material.forEach((material) => material.dispose());
      else object.material?.dispose?.();
    });
    this.modelGroup = null;
  }

  disposeRenderer() {
    this.stopLoop();
    this.resizeObserver?.disconnect();
    this.disposeModel();
    this.controls?.dispose?.();
    this.renderer?.dispose?.();
    this.renderer?.domElement?.remove();
    this.renderer = null;
  }

  dispose() {
    this.disposeRenderer();
    this.scene = null;
    this.camera = null;
    this.controls = null;
  }
}

/**
 * 8번 모델 탭과 10번 연결 성분 뷰어를 관리한다.
 * 자동 경로 로드는 HTTP 서버에서, 직접 파일 선택은 file://에서도 동작한다.
 */
class STLViewerManager {
  constructor() {
    this.modelViewer = null;
    this.componentViewer = null;
    this.currentModelId = "arch-01";
    this.modelManifest = null;
    this.componentFiles = { stl: null, json: null };
  }

  async initialize() {
    const modelContainer = document.getElementById("model-viewer");
    const componentContainer = document.getElementById("component-viewer");

    if (modelContainer) {
      this.modelViewer = new ResearchSTLViewer(modelContainer);
      this.modelViewer.initialize();
    }

    if (componentContainer) {
      this.componentViewer = new ResearchSTLViewer(componentContainer, {
        legend: document.getElementById("component-legend")
      });
      this.componentViewer.initialize();
    }

    this.bindModelControls();
    this.bindComponentControls();
    this.bindSlideLifecycle();
    await this.loadManifest();
  }

  async loadManifest() {
    if (window.location.protocol === "file:") return;
    try {
      const response = await fetch("assets/data/model-manifest.json", { cache: "no-store" });
      if (response.ok) this.modelManifest = await response.json();
      const item = this.findManifestItem(this.currentModelId);
      if (item?.available) {
        this.modelViewer?.loadFromUrls(`assets/models/${item.stl}`);
      }
    } catch (error) {
      // 자리표시자 상태를 유지한다.
    }
  }

  bindModelControls() {
    const tabs = Array.from(document.querySelectorAll(".model-tabs [data-model]"));
    const expected = document.getElementById("model-expected-name");
    const fileInput = document.getElementById("model-file-input");
    const pathLoad = document.getElementById("model-path-load");
    const cameraReset = document.getElementById("model-camera-reset");

    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        tabs.forEach((item) => item.classList.toggle("active", item === tab));
        this.currentModelId = tab.dataset.model;
        const fileName = `${this.currentModelId}.stl`;
        if (expected) expected.textContent = fileName;

        const item = this.findManifestItem(this.currentModelId);
        if (item?.available && window.location.protocol !== "file:") {
          this.modelViewer?.loadFromUrls(`assets/models/${item.stl}`);
        } else {
          this.modelViewer?.showPlaceholder("STL 모델 파일 추가 예정", fileName);
        }
      });
    });

    fileInput?.addEventListener("change", () => {
      const file = fileInput.files?.[0];
      if (file) this.modelViewer?.loadFromFiles(file);
    });

    pathLoad?.addEventListener("click", () => {
      const item = this.findManifestItem(this.currentModelId);
      const stlName = item?.stl || `${this.currentModelId}.stl`;
      this.modelViewer?.loadFromUrls(`assets/models/${stlName}`);
    });

    cameraReset?.addEventListener("click", () => this.modelViewer?.resetCamera());
  }

  bindComponentControls() {
    const stlInput = document.getElementById("component-stl-input");
    const jsonInput = document.getElementById("component-json-input");
    const apply = document.getElementById("component-files-load");
    const pathLoad = document.getElementById("component-path-load");

    stlInput?.addEventListener("change", () => {
      this.componentFiles.stl = stlInput.files?.[0] || null;
    });
    jsonInput?.addEventListener("change", () => {
      this.componentFiles.json = jsonInput.files?.[0] || null;
    });

    apply?.addEventListener("click", () => {
      if (!this.componentFiles.stl || !this.componentFiles.json) {
        this.componentViewer?.showPlaceholder("STL과 components.json을 모두 선택하세요.");
        return;
      }
      this.componentViewer?.loadFromFiles(this.componentFiles.stl, this.componentFiles.json);
    });

    pathLoad?.addEventListener("click", () => {
      this.componentViewer?.loadFromUrls(
        "assets/models/모래시계model.stl",
        "assets/data/모래시계model.components.json"
      );
    });
  }

  bindSlideLifecycle() {
    document.addEventListener("presentation:slidechange", (event) => {
      const slideId = event.detail.slideId;
      this.modelViewer?.setActive(slideId === "slide-8");
      this.componentViewer?.setActive(slideId === "slide-10");
      if (slideId === "slide-10" && !this.componentViewer?.modelGroup) {
        this.componentViewer?.loadFromUrls(
          "assets/models/모래시계model.stl",
          "assets/data/모래시계model.components.json"
        );
      }
    });

    window.addEventListener("pagehide", () => {
      this.modelViewer?.dispose();
      this.componentViewer?.dispose();
    }, { once: true });
  }

  findManifestItem(id) {
    return this.modelManifest?.models?.find((item) => item.id === id) || null;
  }
}

window.addEventListener("DOMContentLoaded", () => {
  const manager = new STLViewerManager();
  window.stlViewerManager = manager;
  manager.initialize();
});
