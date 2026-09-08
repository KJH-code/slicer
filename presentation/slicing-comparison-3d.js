/* global THREE */

/**
 * 4번 슬라이드의 평면·경사면·원뿔면·구면 슬라이싱을 비교한다.
 *
 * - 네 장면은 같은 STL과 고정 카메라를 사용한다.
 * - 평면·경사·원뿔은 현재 슬라이싱 면을 크게 표시한다.
 * - 곡면은 STL 내부의 채운 단면과 외곽선만 표시한다.
 * - 현재 단면은 밝게, 지나간 단면과 교선은 방식별 색으로 누적 표시한다.
 * - 평면 교선은 삼각형 변에서, 비선형 교선은 채운 단면의 외곽에서 계산한다.
 * - 단면 내부는 수직 광선의 홀짝 판정으로 STL 내부를 채운다.
 */
(() => {
  "use strict";

  const MODEL_URL = "assets/models/slicing-comparison-model.stl";
  const MODEL_LEVEL_COUNT = 7;
  const STEP_DURATION_MS = 920;
  const LAST_LAYER_HOLD_MS = 1250;
  const SURFACE_SIZE = 136;
  const SECTION_GRID_DIVISIONS = 56;
  const CURVED_CENTER = { x: 0, y: 0, z: -30 };

  const METHOD_CONFIGS = {
    planar: {
      color: 0x63b3ff,
      scalar: (x, y, z) => z,
      surfaceZ: (x, y, level) => level,
      createSurface: (level, color) => createPlanarSurface(level, color, 0)
    },
    angled: {
      color: 0xff9d45,
      angleRad: THREE.MathUtils.degToRad(20),
      scalar(x, y, z) {
        return z - Math.tan(this.angleRad) * x;
      },
      surfaceZ(x, y, level) {
        return level + Math.tan(this.angleRad) * x;
      },
      createSurface(level, color) {
        return createPlanarSurface(level, color, -this.angleRad);
      }
    },
    conical: {
      color: 0x2de2c5,
      angleRad: THREE.MathUtils.degToRad(30),
      levelRange: {
        start: 15,
        end: 50,
        normalSpacing: 5
      },
      scalar(x, y, z) {
        return z + Math.tan(this.angleRad) * Math.hypot(x, y);
      },
      surfaceZ(x, y, level) {
        return level - Math.tan(this.angleRad) * Math.hypot(x, y);
      },
      levelStep() {
        return this.levelRange.normalSpacing / Math.cos(this.angleRad);
      },
      createSurface(level, color) {
        return createConicalSurface(level, color, this.angleRad);
      }
    },
    curved: {
      color: 0xb99cff,
      levelRange: {
        start: 30,
        end: 70,
        normalSpacing: 5
      },
      scalar: (x, y, z) => Math.hypot(
        x - CURVED_CENTER.x,
        y - CURVED_CENTER.y,
        z - CURVED_CENTER.z
      ),
      surfaceZ(x, y, radius) {
        const dx = x - CURVED_CENTER.x;
        const dy = y - CURVED_CENTER.y;
        const heightSquared = radius * radius - dx * dx - dy * dy;
        if (heightSquared < 0) return null;
        return CURVED_CENTER.z + Math.sqrt(Math.max(0, heightSquared));
      },
      levelStep() {
        return this.levelRange.normalSpacing;
      },
      createSurface: () => createHiddenSurfaceGroup()
    }
  };

  function createSurfaceMaterial(color) {
    return new THREE.MeshBasicMaterial({
      color,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.22,
      depthWrite: false
    });
  }

  function createSurfaceRim(geometry, color) {
    const rimGeometry = new THREE.EdgesGeometry(geometry, 38);
    const rimMaterial = new THREE.LineBasicMaterial({
      color,
      transparent: true,
      opacity: 0.52,
      depthWrite: false
    });
    const rim = new THREE.LineSegments(rimGeometry, rimMaterial);
    rim.renderOrder = 3;
    return rim;
  }

  function createSurfaceGroup(geometry, color) {
    const group = new THREE.Group();
    const surface = new THREE.Mesh(geometry, createSurfaceMaterial(color));
    const rim = createSurfaceRim(geometry, color);
    surface.renderOrder = 2;
    group.add(surface, rim);
    group.userData.surfaceMaterial = surface.material;
    group.userData.rimMaterial = rim.material;
    group.userData.guideMaterial = null;
    group.visible = false;
    return group;
  }

  function createPlanarSurface(level, color, rotationY) {
    const geometry = new THREE.PlaneGeometry(SURFACE_SIZE, SURFACE_SIZE);
    const group = createSurfaceGroup(geometry, color);
    group.rotation.y = rotationY;
    group.position.z = level;
    return group;
  }

  function createHiddenSurfaceGroup() {
    const group = new THREE.Group();
    group.visible = false;
    return group;
  }

  function createConicalSurface(level, color, angleRad) {
    const fullRadius = SURFACE_SIZE * 0.53;
    const tangent = Math.tan(angleRad);
    const clippingEpsilon = 1e-4;
    // z = level - r tan(angle) >= 0을 만족하는 반경까지만 생성한다.
    const radius = Math.min(
      fullRadius,
      Math.max(0, (level - clippingEpsilon) / tangent)
    );
    const radialSegments = 18;
    const angularSegments = 72;
    const positions = [0, 0, 0];
    const indices = [];

    for (let ring = 1; ring <= radialSegments; ring += 1) {
      const ringRadius = radius * ring / radialSegments;
      const ringZ = -ringRadius * tangent;
      for (let segment = 0; segment < angularSegments; segment += 1) {
        const phi = Math.PI * 2 * segment / angularSegments;
        positions.push(
          ringRadius * Math.cos(phi),
          ringRadius * Math.sin(phi),
          ringZ
        );
      }
    }

    for (let segment = 0; segment < angularSegments; segment += 1) {
      indices.push(
        0,
        1 + segment,
        1 + (segment + 1) % angularSegments
      );
    }

    for (let ring = 1; ring < radialSegments; ring += 1) {
      const innerStart = 1 + (ring - 1) * angularSegments;
      const outerStart = 1 + ring * angularSegments;
      for (let segment = 0; segment < angularSegments; segment += 1) {
        const next = (segment + 1) % angularSegments;
        indices.push(
          innerStart + segment,
          outerStart + segment,
          outerStart + next,
          innerStart + segment,
          outerStart + next,
          innerStart + next
        );
      }
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(positions, 3)
    );
    geometry.setIndex(indices);
    geometry.computeVertexNormals();
    const group = createSurfaceGroup(geometry, color);

    const guidePositions = [];
    [0.25, 0.5, 0.75, 1].forEach((ratio) => {
      const guideRadius = radius * ratio;
      const guideZ = -guideRadius * tangent;
      for (let segment = 0; segment < angularSegments; segment += 1) {
        const phiA = Math.PI * 2 * segment / angularSegments;
        const phiB = Math.PI * 2 * (segment + 1) / angularSegments;
        guidePositions.push(
          guideRadius * Math.cos(phiA),
          guideRadius * Math.sin(phiA),
          guideZ,
          guideRadius * Math.cos(phiB),
          guideRadius * Math.sin(phiB),
          guideZ
        );
      }
    });

    for (let segment = 0; segment < 12; segment += 1) {
      const phi = Math.PI * 2 * segment / 12;
      guidePositions.push(
        0, 0, 0,
        radius * Math.cos(phi),
        radius * Math.sin(phi),
        -radius * tangent
      );
    }

    const guideGeometry = new THREE.BufferGeometry();
    guideGeometry.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(guidePositions, 3)
    );
    const guideMaterial = new THREE.LineBasicMaterial({
      color,
      transparent: true,
      opacity: 0.48,
      depthWrite: false
    });
    const guides = new THREE.LineSegments(guideGeometry, guideMaterial);
    guides.renderOrder = 3;
    group.add(guides);
    group.userData.guideMaterial = guideMaterial;

    // 로컬 원점은 꼭짓점이며 z = level - r tan(angle)을 직접 만족한다.
    // radius를 level/tan(angle) 이하로 제한했으므로 월드 좌표 z는 음수가 아니다.
    group.position.z = level;
    return group;
  }

  function createReferenceLine(points, color) {
    const geometry = new THREE.BufferGeometry().setFromPoints(points);
    const material = new THREE.LineDashedMaterial({
      color,
      transparent: true,
      opacity: 0.64,
      dashSize: 3,
      gapSize: 2,
      depthWrite: false
    });
    const line = new THREE.Line(geometry, material);
    line.computeLineDistances();
    return line;
  }

  function setStatus(stage, message, isError = false) {
    const status = stage.querySelector(".slice-3d-status");
    if (status) status.textContent = message;
    stage.classList.toggle("has-error", isError);
    stage.classList.toggle("is-ready", !isError && message === "");
  }

  function pushUniquePoint(points, point, epsilonSquared) {
    if (points.some((item) => item.distanceToSquared(point) <= epsilonSquared)) return;
    points.push(point);
  }

  function interpolateZero(a, b, valueA, valueB) {
    const denominator = valueA - valueB;
    const t = Math.abs(denominator) < 1e-12 ? 0.5 : valueA / denominator;
    return new THREE.Vector3(
      THREE.MathUtils.lerp(a.x, b.x, t),
      THREE.MathUtils.lerp(a.y, b.y, t),
      THREE.MathUtils.lerp(a.z, b.z, t)
    );
  }

  /**
   * 삼각형마다 암시적 함수 scalar(x,y,z)-level의 부호가 바뀌는 변을 찾는다.
   * 각 삼각형 안의 짧은 곡선 구간은 하나의 선분으로 근사한다.
   */
  function createIntersectionGeometry(modelGeometry, config, level, scalarRange) {
    const position = modelGeometry.getAttribute("position");
    const output = [];
    const epsilon = Math.max(1e-5, scalarRange * 1e-7);
    const pointEpsilonSquared = epsilon * epsilon * 16;
    const vertices = [
      new THREE.Vector3(),
      new THREE.Vector3(),
      new THREE.Vector3()
    ];
    const values = [0, 0, 0];
    const edges = [[0, 1], [1, 2], [2, 0]];

    for (let offset = 0; offset < position.count; offset += 3) {
      for (let local = 0; local < 3; local += 1) {
        const vertex = vertices[local];
        vertex.fromBufferAttribute(position, offset + local);
        values[local] = config.scalar.call(config, vertex.x, vertex.y, vertex.z) - level;
      }

      const hits = [];
      edges.forEach(([aIndex, bIndex]) => {
        const a = vertices[aIndex];
        const b = vertices[bIndex];
        const valueA = values[aIndex];
        const valueB = values[bIndex];
        const aOnSurface = Math.abs(valueA) <= epsilon;
        const bOnSurface = Math.abs(valueB) <= epsilon;

        if (aOnSurface) pushUniquePoint(hits, a.clone(), pointEpsilonSquared);
        if (bOnSurface) pushUniquePoint(hits, b.clone(), pointEpsilonSquared);

        if (!aOnSurface && !bOnSurface && valueA * valueB < 0) {
          pushUniquePoint(
            hits,
            interpolateZero(a, b, valueA, valueB),
            pointEpsilonSquared
          );
        }
      });

      if (hits.length < 2) continue;

      // 꼭짓점이 면 위에 놓여 점이 3개 이상이면 가장 긴 두 점을 사용한다.
      let first = hits[0];
      let second = hits[1];
      let longest = first.distanceToSquared(second);
      for (let a = 0; a < hits.length; a += 1) {
        for (let b = a + 1; b < hits.length; b += 1) {
          const distance = hits[a].distanceToSquared(hits[b]);
          if (distance > longest) {
            first = hits[a];
            second = hits[b];
            longest = distance;
          }
        }
      }

      output.push(
        first.x, first.y, first.z,
        second.x, second.y, second.z
      );
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(output, 3)
    );
    if (output.length > 0) geometry.computeBoundingSphere();
    return geometry;
  }

  function scalarBounds(geometry, config) {
    const position = geometry.getAttribute("position");
    let minimum = Infinity;
    let maximum = -Infinity;

    for (let index = 0; index < position.count; index += 1) {
      const value = config.scalar.call(
        config,
        position.getX(index),
        position.getY(index),
        position.getZ(index)
      );
      minimum = Math.min(minimum, value);
      maximum = Math.max(maximum, value);
    }

    return { minimum, maximum };
  }

  function createLevels(bounds, config) {
    if (config.levelRange) {
      const levels = [];
      const step = config.levelStep.call(config);
      for (
        let level = config.levelRange.start;
        level <= config.levelRange.end + 1e-8;
        level += step
      ) {
        levels.push(level);
      }
      return levels;
    }

    const range = bounds.maximum - bounds.minimum;
    const start = bounds.minimum + range * 0.045;
    const end = bounds.maximum - range * 0.045;
    return Array.from({ length: MODEL_LEVEL_COUNT }, (_, index) =>
      THREE.MathUtils.lerp(start, end, index / (MODEL_LEVEL_COUNT - 1))
    );
  }

  /**
   * 닫힌 STL을 XY 격자로 색인하고 +Z 방향 광선의 교차 횟수로 내부를 판정한다.
   * 슬라이싱 면 위의 격자점마다 전체 삼각형을 다시 검사하지 않도록 후보를 줄인다.
   */
  function createVerticalRayIndex(geometry, gridSize = 32) {
    const position = geometry.getAttribute("position");
    const box = geometry.boundingBox.clone();
    const width = Math.max(1e-8, box.max.x - box.min.x);
    const height = Math.max(1e-8, box.max.y - box.min.y);
    const cells = Array.from(
      { length: gridSize * gridSize },
      () => []
    );
    const triangles = [];
    const projectionEpsilon = width * height * 1e-12;
    const barycentricEpsilon = 1e-7;
    const hitEpsilon = Math.max(width, height, box.max.z - box.min.z) * 1e-6;

    const clampCellX = (x) => THREE.MathUtils.clamp(
      Math.floor((x - box.min.x) / width * gridSize),
      0,
      gridSize - 1
    );
    const clampCellY = (y) => THREE.MathUtils.clamp(
      Math.floor((y - box.min.y) / height * gridSize),
      0,
      gridSize - 1
    );

    for (let offset = 0; offset < position.count; offset += 3) {
      const ax = position.getX(offset);
      const ay = position.getY(offset);
      const az = position.getZ(offset);
      const bx = position.getX(offset + 1);
      const by = position.getY(offset + 1);
      const bz = position.getZ(offset + 1);
      const cx = position.getX(offset + 2);
      const cy = position.getY(offset + 2);
      const cz = position.getZ(offset + 2);
      const denominator = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy);

      // 수직 삼각형은 +Z 광선과 한 점으로 교차하지 않으므로 제외한다.
      if (Math.abs(denominator) <= projectionEpsilon) continue;

      const triangle = {
        ax, ay, az,
        bx, by, bz,
        cx, cy, cz,
        denominator,
        minX: Math.min(ax, bx, cx),
        maxX: Math.max(ax, bx, cx),
        minY: Math.min(ay, by, cy),
        maxY: Math.max(ay, by, cy)
      };
      const triangleIndex = triangles.push(triangle) - 1;
      const startX = clampCellX(triangle.minX);
      const endX = clampCellX(triangle.maxX);
      const startY = clampCellY(triangle.minY);
      const endY = clampCellY(triangle.maxY);

      for (let cellY = startY; cellY <= endY; cellY += 1) {
        for (let cellX = startX; cellX <= endX; cellX += 1) {
          cells[cellY * gridSize + cellX].push(triangleIndex);
        }
      }
    }

    return {
      bounds: box,
      contains(x, y, z) {
        if (
          x < box.min.x || x > box.max.x
          || y < box.min.y || y > box.max.y
          || z < box.min.z - hitEpsilon || z > box.max.z + hitEpsilon
        ) {
          return false;
        }

        const cellX = clampCellX(x);
        const cellY = clampCellY(y);
        const candidates = cells[cellY * gridSize + cellX];
        const hits = [];

        candidates.forEach((triangleIndex) => {
          const triangle = triangles[triangleIndex];
          if (
            x < triangle.minX - hitEpsilon
            || x > triangle.maxX + hitEpsilon
            || y < triangle.minY - hitEpsilon
            || y > triangle.maxY + hitEpsilon
          ) {
            return;
          }

          const u = (
            (triangle.by - triangle.cy) * (x - triangle.cx)
            + (triangle.cx - triangle.bx) * (y - triangle.cy)
          ) / triangle.denominator;
          const v = (
            (triangle.cy - triangle.ay) * (x - triangle.cx)
            + (triangle.ax - triangle.cx) * (y - triangle.cy)
          ) / triangle.denominator;
          const w = 1 - u - v;
          if (
            u < -barycentricEpsilon
            || v < -barycentricEpsilon
            || w < -barycentricEpsilon
          ) {
            return;
          }

          const hitZ = u * triangle.az + v * triangle.bz + w * triangle.cz;
          if (Math.abs(hitZ - z) <= hitEpsilon) {
            hits.length = 0;
            hits.push(z);
            hits.onBoundary = true;
            return;
          }
          if (hitZ > z + hitEpsilon) hits.push(hitZ);
        });

        if (hits.onBoundary) return true;
        hits.sort((a, b) => a - b);

        let uniqueHitCount = 0;
        let previous = -Infinity;
        hits.forEach((hit) => {
          if (hit - previous > hitEpsilon) {
            uniqueHitCount += 1;
            previous = hit;
          }
        });
        return uniqueHitCount % 2 === 1;
      }
    };
  }

  function createSectionGeometries(rayIndex, config, level) {
    const box = rayIndex.bounds;
    const divisions = SECTION_GRID_DIVISIONS;
    const cellWidth = (box.max.x - box.min.x) / divisions;
    const cellHeight = (box.max.y - box.min.y) / divisions;
    const fillPositions = [];
    const boundaryPositions = [];
    const occupied = new Uint8Array(divisions * divisions);

    for (let row = 0; row < divisions; row += 1) {
      const y0 = box.min.y + cellHeight * row;
      const y1 = y0 + cellHeight;
      const centerY = (y0 + y1) / 2;

      for (let column = 0; column < divisions; column += 1) {
        const x0 = box.min.x + cellWidth * column;
        const x1 = x0 + cellWidth;
        const centerX = (x0 + x1) / 2;
        const centerZ = config.surfaceZ.call(config, centerX, centerY, level);
        if (centerZ === null || !rayIndex.contains(centerX, centerY, centerZ)) {
          continue;
        }

        const z00 = config.surfaceZ.call(config, x0, y0, level);
        const z10 = config.surfaceZ.call(config, x1, y0, level);
        const z11 = config.surfaceZ.call(config, x1, y1, level);
        const z01 = config.surfaceZ.call(config, x0, y1, level);
        if ([z00, z10, z11, z01].some((value) => value === null)) continue;

        occupied[row * divisions + column] = 1;
        fillPositions.push(
          x0, y0, z00,
          x1, y0, z10,
          x1, y1, z11,
          x0, y0, z00,
          x1, y1, z11,
          x0, y1, z01
        );
      }
    }

    const isOccupied = (column, row) => (
      column >= 0
      && column < divisions
      && row >= 0
      && row < divisions
      && occupied[row * divisions + column] === 1
    );

    for (let row = 0; row < divisions; row += 1) {
      const y0 = box.min.y + cellHeight * row;
      const y1 = y0 + cellHeight;
      for (let column = 0; column < divisions; column += 1) {
        if (!isOccupied(column, row)) continue;
        const x0 = box.min.x + cellWidth * column;
        const x1 = x0 + cellWidth;
        const z00 = config.surfaceZ.call(config, x0, y0, level);
        const z10 = config.surfaceZ.call(config, x1, y0, level);
        const z11 = config.surfaceZ.call(config, x1, y1, level);
        const z01 = config.surfaceZ.call(config, x0, y1, level);

        if (!isOccupied(column, row - 1)) {
          boundaryPositions.push(x0, y0, z00, x1, y0, z10);
        }
        if (!isOccupied(column + 1, row)) {
          boundaryPositions.push(x1, y0, z10, x1, y1, z11);
        }
        if (!isOccupied(column, row + 1)) {
          boundaryPositions.push(x1, y1, z11, x0, y1, z01);
        }
        if (!isOccupied(column - 1, row)) {
          boundaryPositions.push(x0, y1, z01, x0, y0, z00);
        }
      }
    }

    const fillGeometry = new THREE.BufferGeometry();
    fillGeometry.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(fillPositions, 3)
    );
    if (fillPositions.length > 0) fillGeometry.computeBoundingSphere();

    const boundaryGeometry = new THREE.BufferGeometry();
    boundaryGeometry.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(boundaryPositions, 3)
    );
    if (boundaryPositions.length > 0) boundaryGeometry.computeBoundingSphere();

    return { fillGeometry, boundaryGeometry };
  }

  class SlicingMethodScene {
    constructor(stage, type, sourceGeometry, rayIndex) {
      this.stage = stage;
      this.type = type;
      this.config = METHOD_CONFIGS[type];
      this.rayIndex = rayIndex;
      this.canvasHost = stage.querySelector(".slice-3d-canvas");
      this.scene = null;
      this.camera = null;
      this.renderer = null;
      this.modelGeometry = null;
      this.surfaceGroups = [];
      this.intersectionLines = [];
      this.fillMeshes = [];
      this.layerCount = 0;
      this.currentLayer = -1;
      this.resizeObserver = null;
      this.pastLineMaterial = null;
      this.currentLineMaterial = null;
      this.pastFillMaterial = null;
      this.currentFillMaterial = null;
      this.initialized = false;

      this.initialize(sourceGeometry);
    }

    initialize(sourceGeometry) {
      if (!this.config || !this.canvasHost) {
        setStatus(this.stage, "3D 장면 설정을 찾을 수 없습니다.", true);
        return;
      }

      try {
        this.scene = new THREE.Scene();
        this.camera = new THREE.OrthographicCamera(-70, 70, 70, -70, 0.1, 1000);
        this.camera.up.set(0, 0, 1);
        this.camera.position.set(116, -148, 108);
        this.camera.lookAt(0, 0, 12);

        this.renderer = new THREE.WebGLRenderer({
          antialias: true,
          alpha: true,
          powerPreference: "low-power"
        });
        this.renderer.setClearColor(0x07111d, 0);
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.35));
        this.renderer.outputEncoding = THREE.sRGBEncoding;
        this.canvasHost.appendChild(this.renderer.domElement);

        const hemisphere = new THREE.HemisphereLight(0xe5f5ff, 0x102033, 1.28);
        const key = new THREE.DirectionalLight(0xffffff, 1.05);
        const rim = new THREE.DirectionalLight(this.config.color, 0.72);
        key.position.set(75, -90, 130);
        rim.position.set(-90, 65, 75);
        this.scene.add(hemisphere, key, rim);

        const grid = new THREE.GridHelper(136, 17, 0x345c78, 0x213b50);
        grid.rotation.x = Math.PI / 2;
        grid.position.z = -0.6;
        grid.material.transparent = true;
        grid.material.opacity = 0.27;
        grid.material.depthWrite = false;
        this.scene.add(grid);

        this.modelGeometry = sourceGeometry.clone();
        this.modelGeometry.computeVertexNormals();
        const modelMaterial = new THREE.MeshStandardMaterial({
          color: 0x91a9ba,
          roughness: 0.58,
          metalness: 0.12,
          side: THREE.DoubleSide,
          transparent: true,
          opacity: 0.4,
          depthWrite: false
        });
        const model = new THREE.Mesh(this.modelGeometry, modelMaterial);
        model.renderOrder = 1;
        this.scene.add(model);

        this.addMethodReference();
        this.prepareLayers();

        this.resizeObserver = new ResizeObserver(() => this.resize());
        this.resizeObserver.observe(this.stage);
        this.resize();
        this.setLayer(0);
        this.render(0);
        this.initialized = true;
        setStatus(this.stage, "");
      } catch (error) {
        console.error(`[${this.type}] 3D 초기화 오류:`, error);
        setStatus(
          this.stage,
          `3D 오류: ${error?.message || String(error)}`,
          true
        );
        this.dispose();
      }
    }

    addMethodReference() {
      if (this.type === "conical") {
        this.scene.add(createReferenceLine(
          [new THREE.Vector3(0, 0, 0), new THREE.Vector3(0, 0, 66)],
          0xff9d45
        ));
      }
    }

    prepareLayers() {
      const bounds = scalarBounds(this.modelGeometry, this.config);
      const scalarRange = bounds.maximum - bounds.minimum;
      const levels = createLevels(bounds, this.config);
      this.layerCount = levels.length;

      this.pastLineMaterial = new THREE.LineBasicMaterial({
        color: this.config.color,
        transparent: true,
        opacity: 0.54,
        depthWrite: false,
        depthTest: true
      });
      this.currentLineMaterial = new THREE.LineBasicMaterial({
        color: 0xf6fdff,
        transparent: true,
        opacity: 1,
        linewidth: 2,
        depthWrite: false,
        depthTest: false,
        blending: THREE.AdditiveBlending
      });
      this.pastFillMaterial = new THREE.MeshBasicMaterial({
        color: this.config.color,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.24,
        depthWrite: false,
        depthTest: false
      });
      const currentFillColor = new THREE.Color(this.config.color);
      currentFillColor.lerp(new THREE.Color(0xffffff), 0.38);
      this.currentFillMaterial = new THREE.MeshBasicMaterial({
        color: currentFillColor,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.76,
        depthWrite: false,
        depthTest: false,
        blending: THREE.AdditiveBlending
      });

      levels.forEach((level) => {
        const surface = this.config.createSurface.call(
          this.config,
          level,
          this.config.color
        );
        this.scene.add(surface);
        this.surfaceGroups.push(surface);

        const sectionGeometries = createSectionGeometries(
          this.rayIndex,
          this.config,
          level
        );
        const intersectionGeometry = (
          this.type === "conical" || this.type === "curved"
        )
          ? sectionGeometries.boundaryGeometry
          : createIntersectionGeometry(
            this.modelGeometry,
            this.config,
            level,
            scalarRange
          );
        if (this.type !== "conical" && this.type !== "curved") {
          sectionGeometries.boundaryGeometry.dispose();
        }
        const intersection = new THREE.LineSegments(
          intersectionGeometry,
          this.pastLineMaterial
        );
        intersection.visible = false;
        intersection.renderOrder = 5;
        this.scene.add(intersection);
        this.intersectionLines.push(intersection);

        const fill = new THREE.Mesh(
          sectionGeometries.fillGeometry,
          this.pastFillMaterial
        );
        fill.visible = false;
        fill.renderOrder = 4;
        this.scene.add(fill);
        this.fillMeshes.push(fill);
      });
    }

    setLayer(layerIndex) {
      const resolvedLayer = THREE.MathUtils.clamp(
        layerIndex,
        0,
        Math.max(0, this.layerCount - 1)
      );
      if (resolvedLayer === this.currentLayer) return;
      this.currentLayer = resolvedLayer;

      this.surfaceGroups.forEach((surface, index) => {
        surface.visible = this.type !== "curved" && index === resolvedLayer;
      });

      this.intersectionLines.forEach((line, index) => {
        line.visible = index <= resolvedLayer;
        line.material = index === resolvedLayer
          ? this.currentLineMaterial
          : this.pastLineMaterial;
      });

      this.fillMeshes.forEach((fill, index) => {
        fill.visible = index <= resolvedLayer;
        fill.material = index === resolvedLayer
          ? this.currentFillMaterial
          : this.pastFillMaterial;
      });
    }

    resize() {
      if (!this.renderer || !this.camera) return;
      const width = Math.max(1, this.stage.clientWidth || 320);
      const height = Math.max(1, this.stage.clientHeight || 340);
      const aspect = width / height;
      const viewHeight = 142;
      this.camera.left = -(viewHeight * aspect) / 2;
      this.camera.right = (viewHeight * aspect) / 2;
      this.camera.top = viewHeight / 2;
      this.camera.bottom = -viewHeight / 2;
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(width, height, false);
    }

    render(stepProgress) {
      if (!this.renderer || !this.scene || !this.camera) return;
      const fade = THREE.MathUtils.smoothstep(
        Math.min(stepProgress / 0.28, 1),
        0,
        1
      );
      const surface = this.surfaceGroups[this.currentLayer];
      if (surface?.userData.surfaceMaterial) {
        surface.userData.surfaceMaterial.opacity = 0.06 + fade * 0.18;
        surface.userData.rimMaterial.opacity = 0.16 + fade * 0.48;
        if (surface.userData.guideMaterial) {
          surface.userData.guideMaterial.opacity = 0.12 + fade * 0.42;
        }
      }
      if (this.currentLineMaterial) {
        this.currentLineMaterial.opacity = 0.38 + fade * 0.62;
      }
      if (this.currentFillMaterial) {
        this.currentFillMaterial.opacity = 0.28 + fade * 0.48;
      }
      this.renderer.render(this.scene, this.camera);
    }

    dispose() {
      this.resizeObserver?.disconnect();
      this.scene?.traverse((object) => {
        object.geometry?.dispose?.();
        if (Array.isArray(object.material)) {
          object.material.forEach((material) => material.dispose?.());
        } else {
          object.material?.dispose?.();
        }
      });
      this.renderer?.dispose();
      this.renderer?.domElement?.remove();
      this.renderer = null;
      this.scene = null;
    }
  }

  class SlicingComparisonManager {
    constructor() {
      this.stages = Array.from(document.querySelectorAll("[data-slicing-scene]"));
      this.scenes = [];
      this.ready = false;
      this.requestedActive = false;
      this.active = false;
      this.frameId = null;
      this.startedAt = 0;
      this.currentLayer = -1;
      this.maxLayerCount = MODEL_LEVEL_COUNT;
      this.onSlideChange = this.onSlideChange.bind(this);
      this.tick = this.tick.bind(this);
    }

    async initialize() {
      if (this.stages.length === 0) return;
      if (typeof window.THREE === "undefined" || typeof THREE.STLLoader === "undefined") {
        this.failAll("Three.js 또는 STLLoader를 불러오지 못했습니다.");
        return;
      }

      document.addEventListener("presentation:slidechange", this.onSlideChange);
      window.addEventListener("pagehide", () => this.dispose(), { once: true });

      try {
        const response = await fetch(MODEL_URL, { cache: "no-store" });
        if (!response.ok) throw new Error("model-not-found");
        const buffer = await response.arrayBuffer();
        const loader = new THREE.STLLoader();
        const parsed = loader.parse(buffer);
        const geometry = parsed.index ? parsed.toNonIndexed() : parsed;
        geometry.computeBoundingBox();
        geometry.computeBoundingSphere();
        const rayIndex = createVerticalRayIndex(geometry);

        this.scenes = this.stages.map((stage) =>
          new SlicingMethodScene(
            stage,
            stage.dataset.slicingScene,
            geometry,
            rayIndex
          )
        );
        this.maxLayerCount = Math.max(
          ...this.scenes.map((scene) => scene.layerCount)
        );
        geometry.dispose();
        this.ready = this.scenes.some((scene) => scene.initialized);

        if (this.requestedActive || this.isSlideFourVisible()) this.start();
      } catch (error) {
        const message = window.location.protocol === "file:"
          ? "3D 비교는 로컬 HTTP 서버에서 실행하세요."
          : "비교용 STL 모델을 불러오지 못했습니다.";
        this.failAll(message);
      }
    }

    isSlideFourVisible() {
      const slide = document.getElementById("slide-4");
      return Boolean(
        slide?.classList.contains("present")
        || slide?.classList.contains("is-active")
      );
    }

    onSlideChange(event) {
      if (event.detail.slideId === "slide-4") this.start();
      else this.stop();
    }

    start() {
      this.requestedActive = true;
      if (!this.ready || this.active) return;
      this.active = true;
      this.currentLayer = -1;
      this.startedAt = performance.now();
      this.scenes.forEach((scene) => scene.resize());
      this.frameId = window.requestAnimationFrame(this.tick);
    }

    stop() {
      this.requestedActive = false;
      this.active = false;
      if (this.frameId !== null) {
        window.cancelAnimationFrame(this.frameId);
        this.frameId = null;
      }
    }

    tick(now) {
      if (!this.active) {
        this.frameId = null;
        return;
      }

      const movingDuration = this.maxLayerCount * STEP_DURATION_MS;
      const cycleDuration = movingDuration + LAST_LAYER_HOLD_MS;
      const elapsed = (now - this.startedAt) % cycleDuration;
      const layer = Math.min(
        this.maxLayerCount - 1,
        Math.floor(elapsed / STEP_DURATION_MS)
      );
      const stepProgress = layer === this.maxLayerCount - 1 && elapsed >= movingDuration
        ? 1
        : (elapsed % STEP_DURATION_MS) / STEP_DURATION_MS;

      if (layer !== this.currentLayer) {
        this.currentLayer = layer;
        this.scenes.forEach((scene) => scene.setLayer(layer));
      }

      this.scenes.forEach((scene) => scene.render(stepProgress));
      this.frameId = window.requestAnimationFrame(this.tick);
    }

    failAll(message) {
      this.stages.forEach((stage) => setStatus(stage, message, true));
    }

    dispose() {
      this.stop();
      document.removeEventListener("presentation:slidechange", this.onSlideChange);
      this.scenes.forEach((scene) => scene.dispose());
      this.scenes = [];
    }
  }

  window.addEventListener("DOMContentLoaded", () => {
    const manager = new SlicingComparisonManager();
    window.slicingComparisonManager = manager;
    manager.initialize();
  });
})();