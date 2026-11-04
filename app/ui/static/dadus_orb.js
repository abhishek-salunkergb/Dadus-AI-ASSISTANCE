/**
 * Three.js WebGL Holographic Visualizer Engine for DADUS.
 * Handles audio-reactive waveform deformation, particle ring animation,
 * and state-driven visual feedback (idle, listening, thinking, speaking).
 */

class DadusHolographicOrb {
  constructor(canvasId, options = {}) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) {
      console.error(`[DADUS 3D Engine] Canvas element #${canvasId} not found.`);
      return;
    }

    if (typeof THREE === 'undefined') {
      console.error('[DADUS 3D Engine] Three.js is not loaded. Ensure three.min.js is included.');
      return;
    }

    this.options = Object.assign({
      fov: 42,
      baseScale: 1.0,
      interactive: true,
      zoomable: true
    }, options);

    // Dynamic State: 'idle' | 'listening' | 'thinking' | 'executing' | 'speaking' | 'error' | 'success'
    this.state = 'idle';
    this.targetState = 'idle';
    this.stateProgress = 1.0;

    // Audio Reactivity
    this.audioContext = null;
    this.analyser = null;
    this.audioData = new Uint8Array(64);
    this.audioLevel = 0;
    this.smoothAudioLevel = 0;
    this.isAudioConnected = false;

    // Camera & Interaction Control
    this.rotX = 0.16;
    this.rotY = -0.32;
    this.targetRotX = 0.16;
    this.targetRotY = -0.32;
    this.autoRotSpeed = 0.004;

    this.zoom = 1.0;
    this.targetZoom = 1.0;
    this.minZoom = 0.55;
    this.maxZoom = 1.95;

    this.isDragging = false;
    this.lastMouseX = 0;
    this.lastMouseY = 0;
    this.parallaxX = 0;
    this.parallaxY = 0;

    // Animation Time
    this.time = 0;
    this.clock = new THREE.Clock();

    // Initialize Three.js Scene, Camera, Renderer
    this._initScene();
    this._initLights();
    this._buildVoxelD();
    this._buildSaturnRing();
    this._buildCentralStar();
    this._buildAmbientCubes();
    this._buildEqualizerDais();

    this._bindEvents();
    this._animate = this._animate.bind(this);
    this.animationFrameId = requestAnimationFrame(this._animate);

    console.log('[DADUS 3D Engine] WebGL Hologram initialized successfully.');
  }

  // ==========================================================================
  // 1. Scene, Camera, Renderer Setup
  // ==========================================================================
  _initScene() {
    this.scene = new THREE.Scene();

    const width = this.canvas.clientWidth || window.innerWidth;
    const height = this.canvas.clientHeight || 560;

    this.camera = new THREE.PerspectiveCamera(this.options.fov, width / height, 0.1, 100);
    this.camera.position.set(0, 0, 3.1);

    this.renderer = new THREE.WebGLRenderer({
      canvas: this.canvas,
      antialias: true,
      alpha: true,
      powerPreference: 'high-performance'
    });
    this.renderer.setSize(width, height, false);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.15;

    // Master Group for 3D transformations & tilts
    this.masterGroup = new THREE.Group();
    this.scene.add(this.masterGroup);
  }

  // ==========================================================================
  // 2. Cinematic Bioluminescent Lights
  // ==========================================================================
  _initLights() {
    // Ambient fill
    this.ambientLight = new THREE.AmbientLight(0x0a1428, 1.4);
    this.scene.add(this.ambientLight);

    // Top-Left Electric Cyan Key Light
    this.cyanLight = new THREE.PointLight(0x00f0ff, 2.8, 12);
    this.cyanLight.position.set(-2.8, 2.2, 3.2);
    this.scene.add(this.cyanLight);

    // Bottom-Right Electric Magenta / Violet Rim Light
    this.magentaLight = new THREE.PointLight(0xec4899, 2.4, 12);
    this.magentaLight.position.set(2.8, -1.8, 2.6);
    this.scene.add(this.magentaLight);

    // Deep Cobalt Center Light
    this.centerLight = new THREE.PointLight(0x0077ff, 2.0, 8);
    this.centerLight.position.set(0, 0, 0.5);
    this.masterGroup.add(this.centerLight);
  }

  // ==========================================================================
  // 3. Voxel "D" Construction (InstancedMesh)
  // ==========================================================================
  _buildVoxelD() {
    this.dGroup = new THREE.Group();
    this.masterGroup.add(this.dGroup);

    // Compute voxel positions for the letter "D"
    const voxelCoords = [];
    const step = 0.052;
    const halfZ = 0.12;

    const isInsideD = (x, y, z) => {
      if (Math.abs(z) > halfZ) return false;

      // Vertical spine
      if (x >= -0.72 && x <= -0.38 && y >= -0.92 && y <= 0.92) return true;

      // Top horizontal arm
      if (x >= -0.38 && x <= 0.14 && y >= 0.58 && y <= 0.92) return true;

      // Bottom horizontal arm
      if (x >= -0.38 && x <= 0.14 && y >= -0.92 && y <= -0.58) return true;

      // Outer curve: arc centered at (0.10, 0)
      const cx = 0.10;
      const cy = 0.0;
      const dx = x - cx;
      const dy = y - cy;
      const dist = Math.sqrt(dx * dx + (dy * 1.05) * (dy * 1.05));

      if (dx >= 0 && dist >= 0.52 && dist <= 0.94) {
        return true;
      }

      return false;
    };

    // Sample 3D grid
    for (let x = -0.75; x <= 1.05; x += step) {
      for (let y = -0.95; y <= 0.95; y += step) {
        for (let z = -halfZ; z <= halfZ; z += step) {
          if (isInsideD(x, y, z)) {
            voxelCoords.push({
              x: x + (Math.random() - 0.5) * 0.008,
              y: y + (Math.random() - 0.5) * 0.008,
              z: z + (Math.random() - 0.5) * 0.008,
              baseX: x,
              baseY: y,
              baseZ: z
            });
          }
        }
      }
    }

    this.voxelCount = voxelCoords.length;
    this.voxelData = voxelCoords;

    // Voxel Geometry & Physical Material with Edge Glow
    const cubeSize = 0.046;
    const geometry = new THREE.BoxGeometry(cubeSize, cubeSize, cubeSize);
    const material = new THREE.MeshStandardMaterial({
      roughness: 0.22,
      metalness: 0.82,
      emissive: 0x051226,
      emissiveIntensity: 0.5
    });

    this.instancedMesh = new THREE.InstancedMesh(geometry, material, this.voxelCount);
    this.instancedMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);

    // Per-instance color gradient: Left (Cyan) -> Center (Blue) -> Right (Magenta)
    const dummy = new THREE.Object3D();
    const colorCyan = new THREE.Color(0x00f0ff);
    const colorBlue = new THREE.Color(0x0077ff);
    const colorViolet = new THREE.Color(0xa855f7);
    const colorMagenta = new THREE.Color(0xec4899);

    for (let i = 0; i < this.voxelCount; i++) {
      const v = voxelCoords[i];
      dummy.position.set(v.x, v.y, v.z);
      dummy.updateMatrix();
      this.instancedMesh.setMatrixAt(i, dummy.matrix);

      // Normalized horizontal gradient: [-0.75, 1.0] -> [0, 1]
      const t = Math.max(0, Math.min(1, (v.x + 0.75) / 1.75));
      const col = new THREE.Color();
      if (t < 0.35) {
        col.lerpColors(colorCyan, colorBlue, t / 0.35);
      } else if (t < 0.7) {
        col.lerpColors(colorBlue, colorViolet, (t - 0.35) / 0.35);
      } else {
        col.lerpColors(colorViolet, colorMagenta, (t - 0.7) / 0.3);
      }

      this.instancedMesh.setColorAt(i, col);
    }

    this.instancedMesh.instanceColor.needsUpdate = true;
    this.instancedMesh.instanceMatrix.needsUpdate = true;
    this.dGroup.add(this.instancedMesh);
  }

  // ==========================================================================
  // 4. Saturn Planetary Stardust Ring
  // ==========================================================================
  _buildSaturnRing() {
    this.ringGroup = new THREE.Group();
    // Tilt the orbital ring diagonally at ~28° pitch and -14° roll
    this.ringGroup.rotation.x = THREE.MathUtils.degToRad(28);
    this.ringGroup.rotation.z = THREE.MathUtils.degToRad(-14);
    this.masterGroup.add(this.ringGroup);

    const particleCount = 1100;
    const positions = new Float32Array(particleCount * 3);
    const colors = new Float32Array(particleCount * 3);
    const sizes = new Float32Array(particleCount);

    const colCyan = new THREE.Color(0x00f0ff);
    const colMagenta = new THREE.Color(0xec4899);
    const colWhite = new THREE.Color(0xffffff);

    for (let i = 0; i < particleCount; i++) {
      const angle = (i / particleCount) * Math.PI * 2 + (Math.random() - 0.5) * 0.05;
      // Dense band between radius 1.30 and 1.78
      const radius = 1.32 + Math.pow(Math.random(), 1.5) * 0.44;
      const height = (Math.random() - 0.5) * 0.06;

      positions[i * 3] = Math.cos(angle) * radius;
      positions[i * 3 + 1] = height;
      positions[i * 3 + 2] = Math.sin(angle) * radius;

      // Color follows angle around ring
      const t = (Math.sin(angle) + 1) * 0.5;
      const pColor = new THREE.Color();
      pColor.lerpColors(colCyan, colMagenta, t);
      if (Math.random() < 0.08) {
        pColor.lerp(colWhite, 0.75); // Sparkle stardust
      }

      colors[i * 3] = pColor.r;
      colors[i * 3 + 1] = pColor.g;
      colors[i * 3 + 2] = pColor.b;

      sizes[i] = 0.025 + Math.random() * 0.028;
    }

    const ringGeometry = new THREE.BufferGeometry();
    ringGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    ringGeometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

    const ringMaterial = new THREE.PointsMaterial({
      size: 0.042,
      vertexColors: true,
      transparent: true,
      opacity: 0.88,
      blending: THREE.AdditiveBlending,
      depthWrite: false
    });

    this.ringPoints = new THREE.Points(ringGeometry, ringMaterial);
    this.ringGroup.add(this.ringPoints);
  }

  // ==========================================================================
  // 5. Central 4-Point Radiant Star Flare
  // ==========================================================================
  _buildCentralStar() {
    this.starGroup = new THREE.Group();
    this.starGroup.position.set(0.06, 0.0, 0.0);
    this.masterGroup.add(this.starGroup);

    // Glowing Core Sphere
    const coreGeo = new THREE.SphereGeometry(0.048, 16, 16);
    const coreMat = new THREE.MeshBasicMaterial({
      color: 0xffffff,
      transparent: true,
      opacity: 0.95
    });
    this.starCore = new THREE.Mesh(coreGeo, coreMat);
    this.starGroup.add(this.starCore);

    // 4 Sharp Diamond Rays
    const rayMat = new THREE.MeshBasicMaterial({
      color: 0x80f5ff,
      transparent: true,
      opacity: 0.85,
      blending: THREE.AdditiveBlending
    });

    // Horizontal Flare Ray
    const horizGeo = new THREE.PlaneGeometry(0.55, 0.045);
    const horizFlare = new THREE.Mesh(horizGeo, rayMat);
    this.starGroup.add(horizFlare);

    // Vertical Flare Ray
    const vertGeo = new THREE.PlaneGeometry(0.045, 0.55);
    const vertFlare = new THREE.Mesh(vertGeo, rayMat);
    this.starGroup.add(vertFlare);

    // Diagonal Diamond Core Flare
    const diagGeo = new THREE.PlaneGeometry(0.16, 0.16);
    const diagFlare = new THREE.Mesh(diagGeo, rayMat);
    diagFlare.rotation.z = Math.PI / 4;
    this.starGroup.add(diagFlare);

    // Subtle Outer Halo Disc
    const haloGeo = new THREE.RingGeometry(0.06, 0.18, 32);
    const haloMat = new THREE.MeshBasicMaterial({
      color: 0x00f0ff,
      transparent: true,
      opacity: 0.35,
      blending: THREE.AdditiveBlending,
      side: THREE.DoubleSide
    });
    this.starHalo = new THREE.Mesh(haloGeo, haloMat);
    this.starGroup.add(this.starHalo);
  }

  // ==========================================================================
  // 6. Ambient Floating Volumetric Micro-Cubes
  // ==========================================================================
  _buildAmbientCubes() {
    this.ambientGroup = new THREE.Group();
    this.masterGroup.add(this.ambientGroup);

    this.ambientCubeMeshes = [];
    const cubeCount = 75;
    const cubeGeo = new THREE.BoxGeometry(0.032, 0.032, 0.032);

    const colors = [0x00f0ff, 0x0077ff, 0xa855f7, 0xec4899, 0x38bdf8];

    for (let i = 0; i < cubeCount; i++) {
      const col = colors[Math.floor(Math.random() * colors.length)];
      const cubeMat = new THREE.MeshStandardMaterial({
        color: col,
        emissive: col,
        emissiveIntensity: 0.65,
        roughness: 0.3,
        transparent: true,
        opacity: 0.65 + Math.random() * 0.35
      });

      const mesh = new THREE.Mesh(cubeGeo, cubeMat);

      // Random position in spherical orbital shell around symbol
      const r = 1.35 + Math.random() * 1.5;
      const theta = Math.random() * Math.PI * 2;
      const phi = (Math.random() - 0.5) * Math.PI * 0.75;

      mesh.position.set(
        r * Math.cos(phi) * Math.cos(theta),
        r * Math.sin(phi),
        r * Math.cos(phi) * Math.sin(theta)
      );

      mesh.userData = {
        baseRadius: r,
        baseAngle: theta,
        phi: phi,
        speed: (Math.random() * 0.003 + 0.001) * (Math.random() < 0.5 ? 1 : -1),
        rotX: Math.random() * 0.02 - 0.01,
        rotY: Math.random() * 0.02 - 0.01,
        yFloatFreq: Math.random() * 1.5 + 0.5,
        yFloatAmp: Math.random() * 0.06 + 0.02
      };

      this.ambientCubeMeshes.push(mesh);
      this.ambientGroup.add(mesh);
    }
  }

  // ==========================================================================
  // 7. Live Audio Equalizer Dais (Pedestal Base)
  // ==========================================================================
  _buildEqualizerDais() {
    this.daisGroup = new THREE.Group();
    this.daisGroup.position.set(0, -1.45, 0);
    this.daisGroup.rotation.x = THREE.MathUtils.degToRad(85);
    this.masterGroup.add(this.daisGroup);

    this.eqBarMeshes = [];
    const barCount = 36;
    const barRadius = 1.52;
    const barWidth = 0.045;
    const barDepth = 0.035;

    const baseColorCyan = new THREE.Color(0x00f0ff);
    const baseColorMagenta = new THREE.Color(0xec4899);

    for (let i = 0; i < barCount; i++) {
      const angle = (i / barCount) * Math.PI * 2;
      const geo = new THREE.BoxGeometry(barWidth, 0.08, barDepth);
      // Shift pivot to bottom of box
      geo.translate(0, 0.04, 0);

      const t = (Math.sin(angle) + 1) * 0.5;
      const barCol = new THREE.Color().lerpColors(baseColorCyan, baseColorMagenta, t);

      const mat = new THREE.MeshBasicMaterial({
        color: barCol,
        transparent: true,
        opacity: 0.72
      });

      const bar = new THREE.Mesh(geo, mat);
      bar.position.set(Math.cos(angle) * barRadius, 0, Math.sin(angle) * barRadius);
      bar.lookAt(0, 0, 0);
      bar.rotation.x = Math.PI / 2;

      bar.userData = {
        index: i,
        baseScale: 1.0
      };

      this.eqBarMeshes.push(bar);
      this.daisGroup.add(bar);
    }
  }

  // ==========================================================================
  // 8. Dynamic State & Audio Reactivity
  // ==========================================================================
  setState(state) {
    if (this.state === state) return;
    this.targetState = state;
    this.state = state;
    this.stateProgress = 0.0;
    console.log(`[DADUS 3D Engine] State transitioned to: ${state}`);
  }

  getState() {
    return this.state;
  }

  attachAudioStream(stream) {
    try {
      if (!this.audioContext) {
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
      }
      if (this.audioContext.state === 'suspended') {
        this.audioContext.resume();
      }
      const source = this.audioContext.createMediaStreamSource(stream);
      this.analyser = this.audioContext.createAnalyser();
      this.analyser.fftSize = 128;
      this.analyser.smoothingTimeConstant = 0.8;
      source.connect(this.analyser);
      this.isAudioConnected = true;
      console.log('[DADUS 3D Engine] Microphone stream attached to Web Audio FFT.');
    } catch (e) {
      console.warn('[DADUS 3D Engine] Could not attach audio stream:', e);
    }
  }

  attachAudioElement(audioEl) {
    try {
      if (!this.audioContext) {
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
      }
      if (this.audioContext.state === 'suspended') {
        this.audioContext.resume();
      }
      if (!audioEl._dadusConnected) {
        const source = this.audioContext.createMediaElementSource(audioEl);
        this.analyser = this.audioContext.createAnalyser();
        this.analyser.fftSize = 128;
        this.analyser.smoothingTimeConstant = 0.75;
        source.connect(this.analyser);
        this.analyser.connect(this.audioContext.destination);
        audioEl._dadusConnected = true;
        this.isAudioConnected = true;
        console.log('[DADUS 3D Engine] TTS Audio element attached to Web Audio FFT.');
      }
    } catch (e) {
      console.warn('[DADUS 3D Engine] Could not attach audio element:', e);
    }
  }

  _updateAudio() {
    if (this.analyser) {
      this.analyser.getByteFrequencyData(this.audioData);
      let sum = 0;
      for (let i = 0; i < this.audioData.length; i++) {
        sum += this.audioData[i];
      }
      this.audioLevel = sum / (this.audioData.length * 255);
    } else {
      // Synthetic fallback audio level when active
      if (this.state === 'speaking') {
        this.audioLevel = 0.35 + Math.sin(this.time * 9.5) * 0.25 + Math.sin(this.time * 16.2) * 0.15;
      } else if (this.state === 'listening') {
        this.audioLevel = 0.18 + Math.sin(this.time * 6.0) * 0.12;
      } else {
        this.audioLevel = 0.02;
      }
    }

    this.smoothAudioLevel += (this.audioLevel - this.smoothAudioLevel) * 0.22;
  }

  // ==========================================================================
  // 9. Master Animation Render Loop
  // ==========================================================================
  _animate() {
    this.animationFrameId = requestAnimationFrame(this._animate);

    const delta = this.clock.getDelta();
    this.time += delta;
    this.stateProgress = Math.min(1.0, this.stateProgress + delta * 2.5);

    this._updateAudio();

    // 1. Smooth Rotation & Inertia
    if (!this.isDragging) {
      let speedMult = 1.0;
      if (this.state === 'listening') speedMult = 1.5;
      if (this.state === 'thinking') speedMult = 2.4;
      if (this.state === 'executing') speedMult = 3.2;

      this.rotY += this.autoRotSpeed * speedMult;
      // Gentle spring return to neutral tilt
      this.rotX += (0.16 - this.rotX) * 0.02;
    }

    // Parallax damping
    this.targetRotX += (this.rotX + this.parallaxY - this.targetRotX) * 0.12;
    this.targetRotY += (this.rotY + this.parallaxX - this.targetRotY) * 0.12;

    this.masterGroup.rotation.x = this.targetRotX;
    this.masterGroup.rotation.y = this.targetRotY;

    // 2. Smooth Zoom Interpolation
    this.zoom += (this.targetZoom - this.zoom) * 0.1;
    this.camera.position.z = 3.1 / this.zoom;

    // 3. Floating Levitation Sine Wave
    const levitation = Math.sin(this.time * 1.4) * 0.055;
    this.dGroup.position.y = levitation;
    this.starGroup.position.y = levitation;

    // 4. Dynamic State Reactions & Voxel Waves
    let targetDScale = 1.0;
    let ringOrbitSpeed = 0.009;
    let starPulseSpeed = 3.0;

    if (this.state === 'listening') {
      targetDScale = 1.06 + this.smoothAudioLevel * 0.15;
      ringOrbitSpeed = 0.022;
      starPulseSpeed = 5.5;
      this.cyanLight.intensity = 3.4;
      this.magentaLight.intensity = 2.8;
    } else if (this.state === 'thinking') {
      targetDScale = 1.02 + Math.sin(this.time * 5.0) * 0.04;
      ringOrbitSpeed = 0.038;
      starPulseSpeed = 8.0;
      this.cyanLight.intensity = 2.4;
      this.magentaLight.intensity = 3.6;
    } else if (this.state === 'executing') {
      targetDScale = 1.04 + Math.sin(this.time * 8.0) * 0.06;
      ringOrbitSpeed = 0.048;
      starPulseSpeed = 10.0;
      this.cyanLight.intensity = 3.8;
      this.magentaLight.intensity = 3.2;
    } else if (this.state === 'speaking') {
      targetDScale = 1.02 + this.smoothAudioLevel * 0.22;
      ringOrbitSpeed = 0.016;
      starPulseSpeed = 4.5 + this.smoothAudioLevel * 8.0;
      this.cyanLight.intensity = 2.8 + this.smoothAudioLevel * 1.5;
      this.magentaLight.intensity = 2.8 + this.smoothAudioLevel * 1.5;
    } else if (this.state === 'error') {
      targetDScale = 0.98;
      ringOrbitSpeed = 0.004;
      this.cyanLight.color.setHex(0xf43f5e);
      this.magentaLight.color.setHex(0xe11d48);
    } else if (this.state === 'success') {
      targetDScale = 1.08;
      ringOrbitSpeed = 0.028;
      this.cyanLight.color.setHex(0x10b981);
      this.magentaLight.color.setHex(0x00f0ff);
    } else {
      // Idle
      this.cyanLight.color.setHex(0x00f0ff);
      this.magentaLight.color.setHex(0xec4899);
      this.cyanLight.intensity = 2.8;
      this.magentaLight.intensity = 2.4;
    }

    this.dGroup.scale.setScalar(targetDScale);

    // 5. Rotate Saturn Planetary Ring
    if (this.ringGroup) {
      this.ringGroup.rotation.y += ringOrbitSpeed;
    }

    // 6. Pulse & Rotate 4-Point Radiant Star
    if (this.starGroup) {
      const starScale = 0.9 + Math.sin(this.time * starPulseSpeed) * 0.25 + this.smoothAudioLevel * 0.5;
      this.starGroup.scale.setScalar(starScale);
      this.starGroup.rotation.z -= 0.012;
    }

    // 7. Animate Ambient Floating Cubes
    if (this.ambientCubeMeshes) {
      for (let i = 0; i < this.ambientCubeMeshes.length; i++) {
        const mesh = this.ambientCubeMeshes[i];
        const u = mesh.userData;

        u.baseAngle += u.speed;
        mesh.position.x = u.baseRadius * Math.cos(u.phi) * Math.cos(u.baseAngle);
        mesh.position.z = u.baseRadius * Math.cos(u.phi) * Math.sin(u.baseAngle);
        mesh.position.y = u.baseRadius * Math.sin(u.phi) + Math.sin(this.time * u.yFloatFreq) * u.yFloatAmp;

        mesh.rotation.x += u.rotX;
        mesh.rotation.y += u.rotY;
      }
    }

    // 8. Animate Live Audio Equalizer Dais Bars
    if (this.eqBarMeshes) {
      for (let i = 0; i < this.eqBarMeshes.length; i++) {
        const bar = this.eqBarMeshes[i];
        let freqVal = 0.12;

        if (this.audioData && this.audioData.length > 0) {
          const sampleIdx = i % this.audioData.length;
          freqVal = Math.max(0.08, this.audioData[sampleIdx] / 255.0);
        } else {
          freqVal = 0.1 + Math.sin(this.time * 4.0 + i * 0.35) * 0.12;
        }

        const barHeight = Math.max(0.1, freqVal * (this.state === 'speaking' || this.state === 'listening' ? 3.8 : 1.2));
        bar.scale.y += (barHeight - bar.scale.y) * 0.3;
      }
    }

    // 9. Render the Scene
    this.renderer.render(this.scene, this.camera);
  }

  // ==========================================================================
  // 10. Event Listeners: Orbit, Zoom, Resize
  // ==========================================================================
  _bindEvents() {
    window.addEventListener('resize', () => this._handleResize());

    if (window.ResizeObserver && this.canvas.parentElement) {
      this.resizeObserver = new ResizeObserver(() => this._handleResize());
      this.resizeObserver.observe(this.canvas.parentElement);
    }

    if (!this.options.interactive) return;

    // Mouse Drag to Orbit
    this.canvas.addEventListener('mousedown', (e) => {
      this.isDragging = true;
      this.lastMouseX = e.clientX;
      this.lastMouseY = e.clientY;
    });

    window.addEventListener('mousemove', (e) => {
      if (this.isDragging) {
        const dx = e.clientX - this.lastMouseX;
        const dy = e.clientY - this.lastMouseY;
        this.rotY += dx * 0.008;
        this.rotX += dy * 0.008;
        this.lastMouseX = e.clientX;
        this.lastMouseY = e.clientY;
      } else {
        // Subtle Parallax Hover Effect
        const normX = (e.clientX / window.innerWidth) - 0.5;
        const normY = (e.clientY / window.innerHeight) - 0.5;
        this.parallaxX = normX * 0.14;
        this.parallaxY = normY * 0.14;
      }
    });

    window.addEventListener('mouseup', () => {
      this.isDragging = false;
    });

    // Touch Support for Mobile / Tablets
    this.canvas.addEventListener('touchstart', (e) => {
      if (e.touches.length === 1) {
        this.isDragging = true;
        this.lastMouseX = e.touches[0].clientX;
        this.lastMouseY = e.touches[0].clientY;
      }
    }, { passive: true });

    window.addEventListener('touchmove', (e) => {
      if (this.isDragging && e.touches.length === 1) {
        const dx = e.touches[0].clientX - this.lastMouseX;
        const dy = e.touches[0].clientY - this.lastMouseY;
        this.rotY += dx * 0.01;
        this.rotX += dy * 0.01;
        this.lastMouseX = e.touches[0].clientX;
        this.lastMouseY = e.touches[0].clientY;
      }
    }, { passive: true });

    window.addEventListener('touchend', () => {
      this.isDragging = false;
    });

    // Wheel Zoom
    if (this.options.zoomable) {
      this.canvas.addEventListener('wheel', (e) => {
        e.preventDefault();
        const factor = e.deltaY < 0 ? 1.08 : 0.92;
        this.targetZoom = Math.min(this.maxZoom, Math.max(this.minZoom, this.targetZoom * factor));
      }, { passive: false });
    }
  }

  _handleResize() {
    const width = this.canvas.clientWidth || window.innerWidth;
    const height = this.canvas.clientHeight || 560;

    if (this.camera && this.renderer) {
      this.camera.aspect = width / height;
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(width, height, false);
    }
  }

  destroy() {
    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
    }
    if (this.renderer) {
      this.renderer.dispose();
    }
  }
}

// Global Export
window.DadusHolographicOrb = DadusHolographicOrb;
