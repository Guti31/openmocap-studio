from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from backend.kinematics.quaternions import q_identity, q_normalize, q_rotate_vec


class MadgwickFilter:
    """
    Filtro de fusión sensorial Madgwick en convención Y-up (+Y arriba, gravedad = [0, +1, 0] en reposo).
    Soporta modo 6-DOF (IMU) y 9-DOF (MARG) con tasa de muestreo adaptativa.
    """

    def __init__(self, beta: float = 0.08) -> None:
        self.beta = float(beta)
        self.q = q_identity()

    def reset(self, initial_q: Sequence[float] | None = None) -> None:
        self.q = q_normalize(initial_q) if initial_q is not None else q_identity()

    def update(
        self,
        gyro_rad: Sequence[float],
        accel_ms2: Sequence[float],
        mag: Sequence[float] | None = None,
        dt: float = 1.0 / 120.0,
    ) -> np.ndarray:
        dt = max(1e-4, min(0.1, float(dt)))
        gx, gy, gz = float(gyro_rad[0]), float(gyro_rad[1]), float(gyro_rad[2])
        ax, ay, az = float(accel_ms2[0]), float(accel_ms2[1]), float(accel_ms2[2])

        q0, q1, q2, q3 = float(self.q[0]), float(self.q[1]), float(self.q[2]), float(self.q[3])

        # Derivada de orientación por velocidad angular
        q_dot1 = 0.5 * (-q1 * gx - q2 * gy - q3 * gz)
        q_dot2 = 0.5 * (q0 * gx + q2 * gz - q3 * gy)
        q_dot3 = 0.5 * (q0 * gy - q1 * gz + q3 * gx)
        q_dot4 = 0.5 * (q0 * gz + q1 * gy - q2 * gx)

        a_norm = math.sqrt(ax * ax + ay * ay + az * az)
        if a_norm > 1e-4:
            ax /= a_norm
            ay /= a_norm
            az /= a_norm

            # En sistema Y-up, la reacción gravitacional en reposo apunta a [0, +1, 0].
            # Vector rotado por q^-1 del eje +Y mundo:
            # g_est_x = 2*(q1*q2 + q0*q3)
            # g_est_y = q0^2 - q1^2 + q2^2 - q3^2
            # g_est_z = 2*(q2*q3 - q0*q1)
            fx = 2.0 * (q1 * q2 + q0 * q3) - ax
            fy = (q0 * q0 - q1 * q1 + q2 * q2 - q3 * q3) - ay
            fz = 2.0 * (q2 * q3 - q0 * q1) - az

            # Jacobiano transpuesto J^T * f
            s0 = 2.0 * q3 * fx + 2.0 * q0 * fy - 2.0 * q1 * fz
            s1 = 2.0 * q2 * fx - 2.0 * q1 * fy - 2.0 * q0 * fz
            s2 = 2.0 * q1 * fx + 2.0 * q2 * fy + 2.0 * q3 * fz
            s3 = 2.0 * q0 * fx - 2.0 * q3 * fy + 2.0 * q2 * fz

            if mag is not None:
                mx, my, mz = float(mag[0]), float(mag[1]), float(mag[2])
                m_norm = math.sqrt(mx * mx + my * my + mz * mz)
                if m_norm > 1e-4:
                    mx /= m_norm
                    my /= m_norm
                    mz /= m_norm
                    # Proyectar campo magnético al marco mundo para eliminar inclinación vertical (+Y)
                    h = q_rotate_vec(self.q, [mx, my, mz])
                    bz = math.hypot(float(h[0]), float(h[2]))
                    by = float(h[1])
                    # Referencia horizontal en +Z y vertical en +Y: b = [0, by, bz]
                    # Estimación rotada por q^-1 de [0, by, bz]:
                    ex = by * (2.0 * (q1 * q2 + q0 * q3)) + bz * (2.0 * (q1 * q3 - q0 * q2)) - mx
                    ey = by * (q0 * q0 - q1 * q1 + q2 * q2 - q3 * q3) + bz * (2.0 * (q2 * q3 + q0 * q1)) - my
                    ez = by * (2.0 * (q2 * q3 - q0 * q1)) + bz * (q0 * q0 - q1 * q1 - q2 * q2 + q3 * q3) - mz

                    s0 += by * (2.0 * q3 * ex + 2.0 * q0 * ey - 2.0 * q1 * ez) + bz * (-2.0 * q2 * ex + 2.0 * q1 * ey + 2.0 * q0 * ez)
                    s1 += by * (2.0 * q2 * ex - 2.0 * q1 * ey - 2.0 * q0 * ez) + bz * (2.0 * q3 * ex + 2.0 * q0 * ey - 2.0 * q1 * ez)
                    s2 += by * (2.0 * q1 * ex + 2.0 * q2 * ey + 2.0 * q3 * ez) + bz * (-2.0 * q0 * ex + 2.0 * q3 * ey - 2.0 * q2 * ez)
                    s3 += by * (2.0 * q0 * ex - 2.0 * q3 * ey + 2.0 * q2 * ez) + bz * (2.0 * q1 * ex + 2.0 * q2 * ey + 2.0 * q3 * ez)

            s_norm = math.sqrt(s0 * s0 + s1 * s1 + s2 * s2 + s3 * s3)
            if s_norm > 1e-12:
                inv_s = self.beta / s_norm
                q_dot1 -= s0 * inv_s
                q_dot2 -= s1 * inv_s
                q_dot3 -= s2 * inv_s
                q_dot4 -= s3 * inv_s

        q0 += q_dot1 * dt
        q1 += q_dot2 * dt
        q2 += q_dot3 * dt
        q3 += q_dot4 * dt
        self.q = q_normalize([q0, q1, q2, q3])
        return self.q.copy()


class MahonyFilter:
    """Filtro complementario PI de Mahony de respaldo para microcontroladores y señales ruidosas."""

    def __init__(self, kp: float = 1.0, ki: float = 0.05) -> None:
        self.kp = float(kp)
        self.ki = float(ki)
        self.q = q_identity()
        self.integral_fb = np.zeros(3, dtype=np.float64)

    def reset(self, initial_q: Sequence[float] | None = None) -> None:
        self.q = q_normalize(initial_q) if initial_q is not None else q_identity()
        self.integral_fb.fill(0.0)

    def update(
        self,
        gyro_rad: Sequence[float],
        accel_ms2: Sequence[float],
        dt: float = 1.0 / 120.0,
    ) -> np.ndarray:
        dt = max(1e-4, min(0.1, float(dt)))
        gx, gy, gz = float(gyro_rad[0]), float(gyro_rad[1]), float(gyro_rad[2])
        acc = np.asarray(accel_ms2, dtype=np.float64)
        a_norm = float(np.linalg.norm(acc))
        if a_norm > 1e-4:
            acc = acc / a_norm
            q0, q1, q2, q3 = float(self.q[0]), float(self.q[1]), float(self.q[2]), float(self.q[3])
            v = np.array(
                [
                    2.0 * (q1 * q2 + q0 * q3),
                    q0 * q0 - q1 * q1 + q2 * q2 - q3 * q3,
                    2.0 * (q2 * q3 - q0 * q1),
                ],
                dtype=np.float64,
            )
            err = np.cross(acc, v)
            if self.ki > 0.0:
                self.integral_fb += self.ki * err * dt
            else:
                self.integral_fb.fill(0.0)
            gx += self.kp * float(err[0]) + float(self.integral_fb[0])
            gy += self.kp * float(err[1]) + float(self.integral_fb[1])
            gz += self.kp * float(err[2]) + float(self.integral_fb[2])

        q0, q1, q2, q3 = float(self.q[0]), float(self.q[1]), float(self.q[2]), float(self.q[3])
        dq0 = 0.5 * (-q1 * gx - q2 * gy - q3 * gz)
        dq1 = 0.5 * (q0 * gx + q2 * gz - q3 * gy)
        dq2 = 0.5 * (q0 * gy - q1 * gz + q3 * gx)
        dq3 = 0.5 * (q0 * gz + q1 * gy - q2 * gx)
        self.q = q_normalize([q0 + dq0 * dt, q1 + dq1 * dt, q2 + dq2 * dt, q3 + dq3 * dt])
        return self.q.copy()


class SensorFusionBank:
    """Administra instancias independientes de fusión Madgwick/Mahony por cada sensor_id."""

    def __init__(self, algorithm: str = "madgwick", beta: float = 0.08) -> None:
        self.algorithm = algorithm
        self.beta = beta
        self._filters: dict[str, MadgwickFilter | MahonyFilter] = {}
        self._last_ts: dict[str, float] = {}

    def update_sensor(
        self,
        sensor_id: str,
        gyro_rad: Sequence[float],
        accel_ms2: Sequence[float],
        mag: Sequence[float] | None,
        timestamp_ms: float,
    ) -> np.ndarray:
        if sensor_id not in self._filters:
            self._filters[sensor_id] = (
                MadgwickFilter(beta=self.beta)
                if self.algorithm == "madgwick"
                else MahonyFilter()
            )
            self._last_ts[sensor_id] = timestamp_ms
            dt = 1.0 / 120.0
        else:
            dt = max(1e-4, min(0.1, (timestamp_ms - self._last_ts[sensor_id]) / 1000.0))
            self._last_ts[sensor_id] = timestamp_ms

        flt = self._filters[sensor_id]
        if isinstance(flt, MadgwickFilter):
            return flt.update(gyro_rad, accel_ms2, mag=mag, dt=dt)
        return flt.update(gyro_rad, accel_ms2, dt=dt)

    def reset_sensor(self, sensor_id: str) -> None:
        if sensor_id in self._filters:
            self._filters[sensor_id].reset()

