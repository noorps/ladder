"""a small prng that the browser simulation reproduces bit for bit.

mulberry32 over 32-bit ints, box-muller normals, lognormal by mean and coefficient of
variation. every station owns one stream seeded from (seed, station index), so the draw
sequence does not depend on event ordering and the python and js simulators see the
same service times.
"""
import math

MASK = 0xFFFFFFFF


class Mulberry32:
    def __init__(self, seed):
        self.a = seed & MASK

    def random(self):
        self.a = (self.a + 0x6D2B79F5) & MASK
        a = self.a
        t = ((a ^ (a >> 15)) * (1 | a)) & MASK
        t = ((t + (((t ^ (t >> 7)) * (61 | t)) & MASK)) ^ t) & MASK
        return ((t ^ (t >> 14)) & MASK) / 4294967296.0

    def normal(self):
        u1 = self.random()
        u2 = self.random()
        if u1 < 1e-12:
            u1 = 1e-12
        return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def station_seed(seed, k):
    return (seed * 1000003 + 7919 * (k + 1)) & MASK


class LognormalDraw:
    """service time with the given mean and cv; cv == 0 returns the mean without drawing."""

    def __init__(self, mean, cv, seed):
        self.mean = float(mean)
        self.cv = float(cv)
        self.rng = Mulberry32(seed)
        if cv > 0:
            self.sigma = math.sqrt(math.log(1.0 + cv * cv))
            self.mu = math.log(self.mean) - 0.5 * self.sigma * self.sigma

    def __call__(self):
        if self.cv <= 0:
            return self.mean
        return math.exp(self.mu + self.sigma * self.rng.normal())
