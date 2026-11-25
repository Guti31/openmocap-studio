import React, { useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { Grid, OrbitControls } from '@react-three/drei';
import * as THREE from 'three';
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib';
import { liveFrameRef, useStudioStore } from '../store/useStudioStore';
import type { CameraPreset, RenderMode } from '../types/mocap';

const SEGMENT_RADIUS: Record<string, number> = {
  PELVIS: 0.085,
  SPINE: 0.085,
  SPINE1: 0.088,
  SPINE2: 0.092,
  STERNUM: 0.095,
  NECK: 0.045,
  HEAD: 0.09,
  SHOULDER_L: 0.042,
  SHOULDER_R: 0.042,
  UPPER_ARM_L: 0.044,
  UPPER_ARM_R: 0.044,
  FOREARM_L: 0.036,
  FOREARM_R: 0.036,
  HAND_L: 0.03,
  HAND_R: 0.03,
  THIGH_L: 0.062,
  THIGH_R: 0.062,
  SHIN_L: 0.048,
  SHIN_R: 0.048,
  FOOT_L: 0.04,
  FOOT_R: 0.04,
  TOE_L: 0.032,
  TOE_R: 0.032,
};

const UP_Y = new THREE.Vector3(0, 1, 0);

const CameraRig: React.FC<{
  preset: CameraPreset;
  resetTick: number;
  followPelvis: boolean;
}> = ({ preset, resetTick, followPelvis }) => {
  const controlsRef = useRef<OrbitControlsImpl | null>(null);
  const { camera } = useThree();
  const prevPresetRef = useRef<CameraPreset>(preset);
  const prevTickRef = useRef<number>(resetTick);
  const targetVec = useMemo(() => new THREE.Vector3(), []);

  useFrame(() => {
    const controls = controlsRef.current;
    if (!controls) return;

    const frame = liveFrameRef.current;
    const pelvis = frame?.segments?.PELVIS?.pos ?? [0, 0.95, 0];

    if (prevPresetRef.current !== preset || prevTickRef.current !== resetTick) {
      prevPresetRef.current = preset;
      prevTickRef.current = resetTick;
      targetVec.set(pelvis[0], pelvis[1], pelvis[2]);
      if (preset === 'front') {
        camera.position.set(targetVec.x, targetVec.y + 0.1, targetVec.z + 2.7);
      } else if (preset === 'side') {
        camera.position.set(targetVec.x + 2.7, targetVec.y + 0.1, targetVec.z);
      } else if (preset === 'top') {
        camera.position.set(targetVec.x, targetVec.y + 3.2, targetVec.z + 0.05);
      } else {
        camera.position.set(targetVec.x + 2.1, targetVec.y + 0.7, targetVec.z + 2.4);
      }
      controls.target.copy(targetVec);
      controls.update();
    } else if (followPelvis) {
      targetVec.set(pelvis[0], pelvis[1], pelvis[2]);
      controls.target.lerp(targetVec, 0.18);
      controls.update();
    }
  });

  return (
    <OrbitControls
      ref={controlsRef}
      makeDefault
      enableDamping
      dampingFactor={0.08}
      minDistance={0.8}
      maxDistance={10}
      maxPolarAngle={Math.PI * 0.495}
    />
  );
};

interface MannequinSceneProps {
  renderMode: RenderMode;
  showAxes: boolean;
  showAccel: boolean;
  cameraPreset: CameraPreset;
  cameraResetTick: number;
  followPelvis: boolean;
}

export const MannequinScene: React.FC<MannequinSceneProps> = ({
  renderMode,
  showAxes,
  showAccel,
  cameraPreset,
  cameraResetTick,
  followPelvis,
}) => {
  const selectedSegment = useStudioStore((s) => s.selectedSegment);
  const lastShake = useStudioStore((s) => s.lastShake);
  const activeProfile = useStudioStore((s) => s.activeProfile);

  const jointSpheresRef = useRef<Record<string, THREE.Mesh | null>>({});
  const limbMeshesRef = useRef<Record<string, THREE.Mesh | null>>({});
  const skeletonBonesRef = useRef<Record<string, THREE.Mesh | null>>({});
  const axesGroupsRef = useRef<Record<string, THREE.Group | null>>({});
  const accelArrowsRef = useRef<Record<string, THREE.Mesh | null>>({});
  const headMeshRef = useRef<THREE.Group | null>(null);

  const segmentNames = useMemo(() => {
    const base = [
      'PELVIS',
      'SPINE',
      'SPINE1',
      'SPINE2',
      'STERNUM',
      'NECK',
      'HEAD',
      'SHOULDER_L',
      'UPPER_ARM_L',
      'FOREARM_L',
      'HAND_L',
      'SHOULDER_R',
      'UPPER_ARM_R',
      'FOREARM_R',
      'HAND_R',
      'THIGH_L',
      'SHIN_L',
      'FOOT_L',
      'TOE_L',
      'THIGH_R',
      'SHIN_R',
      'FOOT_R',
      'TOE_R',
    ];
    for (const c of activeProfile?.custom_segments ?? []) {
      const upper = c.name.toUpperCase();
      if (!base.includes(upper)) base.push(upper);
    }
    return base;
  }, [activeProfile]);

  const tempStart = useMemo(() => new THREE.Vector3(), []);
  const tempEnd = useMemo(() => new THREE.Vector3(), []);
  const tempMid = useMemo(() => new THREE.Vector3(), []);
  const tempDir = useMemo(() => new THREE.Vector3(), []);
  const tempQuat = useMemo(() => new THREE.Quaternion(), []);
  const tempBoneQuat = useMemo(() => new THREE.Quaternion(), []);
  const tempAccel = useMemo(() => new THREE.Vector3(), []);

  useFrame(() => {
    const frame = liveFrameRef.current;
    if (!frame || !frame.segments) return;

    const allNames = frame.skeleton_order?.length ? frame.skeleton_order : segmentNames;

    for (const segName of allNames) {
      const seg = frame.segments[segName];
      if (!seg) continue;

      tempStart.set(seg.pos[0], seg.pos[1], seg.pos[2]);
      tempEnd.set(seg.end_pos[0], seg.end_pos[1], seg.end_pos[2]);
      tempMid.addVectors(tempStart, tempEnd).multiplyScalar(0.5);
      tempDir.subVectors(tempEnd, tempStart);
      const len = Math.max(0.03, tempDir.length());
      tempDir.normalize();
      tempBoneQuat.setFromUnitVectors(UP_Y, tempDir);

      // Cuaternión Hamilton [w, x, y, z] -> THREE.Quaternion(x, y, z, w)
      const [qw, qx, qy, qz] = seg.quat;
      tempQuat.set(qx, qy, qz, qw);

      // Esfera articular
      const jMesh = jointSpheresRef.current[segName];
      if (jMesh) {
        jMesh.position.copy(tempStart);
      }

      // Cabeza estilizada con visor frontal (+Z local)
      if (segName === 'HEAD' && headMeshRef.current) {
        headMeshRef.current.position.copy(tempMid);
        headMeshRef.current.quaternion.copy(tempQuat);
      }

      // Segmento sólido anatómico
      const lMesh = limbMeshesRef.current[segName];
      if (lMesh) {
        lMesh.position.copy(tempMid);
        lMesh.quaternion.copy(tempBoneQuat);
        lMesh.scale.set(1, len, 1);
      }

      // Hueso de esqueleto fino
      const bMesh = skeletonBonesRef.current[segName];
      if (bMesh) {
        bMesh.position.copy(tempMid);
        bMesh.quaternion.copy(tempBoneQuat);
        bMesh.scale.set(1, len, 1);
      }

      // Tríada de ejes locales
      const axGroup = axesGroupsRef.current[segName];
      if (axGroup) {
        axGroup.visible = showAxes;
        if (showAxes) {
          axGroup.position.copy(tempStart);
          axGroup.quaternion.copy(tempQuat);
        }
      }

      // Vector de aceleración libre
      const accMesh = accelArrowsRef.current[segName];
      if (accMesh) {
        tempAccel.set(seg.accel[0], seg.accel[1], seg.accel[2]);
        const mag = tempAccel.length();
        accMesh.visible = showAccel && mag > 0.08;
        if (accMesh.visible) {
          const arrowLen = Math.min(0.8, mag * 0.12);
          tempAccel.normalize();
          accMesh.quaternion.setFromUnitVectors(UP_Y, tempAccel);
          accMesh.position.copy(tempMid).addScaledVector(tempAccel, arrowLen * 0.5);
          accMesh.scale.set(1, arrowLen, 1);
        }
      }
    }
  });

  const showMannequin = renderMode === 'mannequin' || renderMode === 'hybrid';
  const showSkeleton = renderMode === 'skeleton' || renderMode === 'hybrid';

  return (
    <>
      <color attach="background" args={['#0b0f17']} />
      <fog attach="fog" args={['#0b0f17', 7, 18]} />

      <ambientLight intensity={0.48} />
      <directionalLight
        position={[3.5, 5.5, 4.0]}
        intensity={1.35}
        castShadow
        shadow-mapSize-width={2048}
        shadow-mapSize-height={2048}
        shadow-camera-near={0.5}
        shadow-camera-far={15}
        shadow-camera-left={-3}
        shadow-camera-right={3}
        shadow-camera-top={3}
        shadow-camera-bottom={-3}
      />
      <directionalLight position={[-3, 2, -2]} intensity={0.45} color="#38bdf8" />

      {/* Piso receptor de sombras + cuadrícula de estudio */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.002, 0]} receiveShadow>
        <planeGeometry args={[24, 24]} />
        <meshStandardMaterial color="#0f1522" roughness={0.9} metalness={0.05} />
      </mesh>
      <Grid
        args={[16, 16]}
        cellSize={0.25}
        cellThickness={0.5}
        cellColor="#1e293b"
        sectionSize={1}
        sectionThickness={1}
        sectionColor="#334155"
        fadeDistance={12}
        position={[0, 0, 0]}
      />
      <axesHelper args={[0.35]} />

      {/* Maniquí y Esqueleto */}
      <group>
        {segmentNames.map((segName) => {
          const isSelected = selectedSegment === segName;
          const isShaking = lastShake?.segment === segName;
          const rad = SEGMENT_RADIUS[segName] ?? 0.04;
          const accentColor = isShaking
            ? '#f59e0b'
            : isSelected
            ? '#06b6d4'
            : '#3b82f6';

          return (
            <React.Fragment key={segName}>
              {/* Articulación */}
              <mesh
                ref={(el) => {
                  jointSpheresRef.current[segName] = el;
                }}
                castShadow
              >
                <sphereGeometry args={[segName === 'PELVIS' ? 0.055 : 0.032, 16, 16]} />
                <meshStandardMaterial
                  color={isSelected ? '#22d3ee' : '#e2e8f0'}
                  emissive={isSelected ? '#06b6d4' : '#0f172a'}
                  emissiveIntensity={isSelected ? 0.6 : 0.15}
                  roughness={0.3}
                />
              </mesh>

              {/* Malla sólida anatómica */}
              {segName !== 'HEAD' ? (
                <mesh
                  ref={(el) => {
                    limbMeshesRef.current[segName] = el;
                  }}
                  visible={showMannequin}
                  castShadow
                  receiveShadow
                >
                  <capsuleGeometry args={[rad * 0.72, Math.max(0.05, 1.0 - 2.0 * rad * 0.72), 8, 16]} />
                  <meshStandardMaterial
                    color={isShaking ? '#f59e0b' : isSelected ? '#0891b2' : '#475569'}
                    roughness={0.45}
                    metalness={0.25}
                    transparent={renderMode === 'hybrid'}
                    opacity={renderMode === 'hybrid' ? 0.42 : 0.96}
                  />
                </mesh>
              ) : (
                <group
                  ref={(el) => {
                    headMeshRef.current = el;
                  }}
                  visible={showMannequin}
                >
                  <mesh castShadow>
                    <sphereGeometry args={[0.095, 20, 20]} />
                    <meshStandardMaterial
                      color="#64748b"
                      roughness={0.4}
                      metalness={0.2}
                      transparent={renderMode === 'hybrid'}
                      opacity={renderMode === 'hybrid' ? 0.48 : 0.96}
                    />
                  </mesh>
                  {/* Visor frontal orientativo (+Z) */}
                  <mesh position={[0, 0.01, 0.082]}>
                    <boxGeometry args={[0.11, 0.035, 0.03]} />
                    <meshStandardMaterial color="#06b6d4" emissive="#06b6d4" emissiveIntensity={0.4} />
                  </mesh>
                </group>
              )}

              {/* Hueso esquelético de precisión */}
              <mesh
                ref={(el) => {
                  skeletonBonesRef.current[segName] = el;
                }}
                visible={showSkeleton}
                castShadow
              >
                <cylinderGeometry args={[0.014, 0.018, 1, 10]} />
                <meshStandardMaterial
                  color={accentColor}
                  emissive={accentColor}
                  emissiveIntensity={0.28}
                  roughness={0.25}
                />
              </mesh>

              {/* Tríada local RGB */}
              <group
                ref={(el) => {
                  axesGroupsRef.current[segName] = el;
                }}
                visible={false}
              >
                <axesHelper args={[0.16]} />
              </group>

              {/* Vector de aceleración */}
              <mesh
                ref={(el) => {
                  accelArrowsRef.current[segName] = el;
                }}
                visible={false}
              >
                <cylinderGeometry args={[0.008, 0.016, 1, 8]} />
                <meshBasicMaterial color="#f59e0b" />
              </mesh>
            </React.Fragment>
          );
        })}
      </group>

      <CameraRig preset={cameraPreset} resetTick={cameraResetTick} followPelvis={followPelvis} />
    </>
  );
};
