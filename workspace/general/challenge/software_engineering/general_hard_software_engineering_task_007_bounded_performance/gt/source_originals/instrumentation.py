"""Public read-only matching protocol and independently owned logical work."""
import hashlib
import json

PROFILE = 'h047-counted-keys/v1'
KINDS = ('email', 'phone', 'name_region')
COUNTERS = ('catalog_visits', 'query_visits', 'key_probes', 'key_hashes', 'key_equalities', 'id_reads')
ASCII_SPACE = ' \t\r\n\f\v'
PHONE_SEPARATORS = ' +-().\t\r\n\f\v'

def ascii_normalize(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError('fields must be strings or null')
    value = value.strip(ASCII_SPACE)
    value = ''.join(chr(ord(c) + 32) if 'A' <= c <= 'Z' else c for c in value)
    return value or None

def phone_normalize(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError('phone must be string or null')
    value = ''.join(c for c in value if c not in PHONE_SEPARATORS)
    return value if value and all('0' <= c <= '9' for c in value) else None

def normalized_keys(row):
    name = ascii_normalize(row.get('display_name'))
    region = ascii_normalize(row.get('region'))
    return {'email': ascii_normalize(row.get('email')), 'phone': phone_normalize(row.get('phone')),
            'name_region': (name, region) if name is not None and region is not None else None}

class WorkLimitExceeded(BaseException):
    pass

class _Meter:
    __slots__ = ('values', 'maximum', 'exceeded')
    def __init__(self, maximum):
        self.values = {name: 0 for name in COUNTERS}
        self.maximum = maximum
        self.exceeded = False
    def tick(self, name):
        self.values[name] += 1
        if self.maximum is not None and sum(self.values.values()) > self.maximum:
            self.exceeded = True
            raise WorkLimitExceeded('trusted stop-work limit exceeded')

class _Key:
    __slots__ = ('_kind', '_value', '_meter', '_hash')
    def __init__(self, kind, value, meter):
        object.__setattr__(self, '_kind', kind)
        object.__setattr__(self, '_value', value)
        object.__setattr__(self, '_meter', meter)
        first = value[0] if isinstance(value, tuple) else value
        raw = json.dumps([kind, value], ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        # Hash collisions are a normal mapping contract. A small public
        # synthetic namespace guarantees adversarial cases exercise equality.
        number = 19 if first.startswith('collision:') else int.from_bytes(hashlib.sha256(raw).digest()[:8], 'big') % (2**61 - 1)
        object.__setattr__(self, '_hash', number)
    def __setattr__(self, name, value):
        raise TypeError('matching keys are immutable')
    def __hash__(self):
        self._meter.tick('key_hashes')
        return self._hash
    def __eq__(self, other):
        self._meter.tick('key_equalities')
        return isinstance(other, _Key) and self._kind == other._kind and self._value == other._value
    def __repr__(self):
        return '<opaque-match-key>'

class _View:
    __slots__ = ('_id', '_keys', '_meter')
    def __init__(self, identity, row, meter):
        if not isinstance(identity, str):
            raise ValueError('record_id/query_id must be strings')
        object.__setattr__(self, '_id', identity)
        object.__setattr__(self, '_keys', {kind: _Key(kind, value, meter) if value is not None else None
                                        for kind, value in normalized_keys(row).items()})
        object.__setattr__(self, '_meter', meter)
    def __setattr__(self, name, value):
        raise TypeError('records and queries are immutable')
    @property
    def id(self):
        self._meter.tick('id_reads')
        return self._id
    def key(self, kind):
        if kind not in KINDS:
            raise ValueError('unknown matching priority')
        self._meter.tick('key_probes')
        return self._keys[kind]

class _Sequence:
    __slots__ = ('_rows', '_meter', '_counter')
    def __init__(self, rows, meter, counter):
        object.__setattr__(self, '_rows', tuple(rows))
        object.__setattr__(self, '_meter', meter)
        object.__setattr__(self, '_counter', counter)
    def __setattr__(self, name, value):
        raise TypeError('matching sequences are immutable')
    def __len__(self):
        return len(self._rows)
    def __getitem__(self, index):
        if isinstance(index, slice):
            indices = range(*index.indices(len(self._rows)))
            return tuple(self[i] for i in indices)
        row = self._rows[index]
        self._meter.tick(self._counter)
        return row
    def __iter__(self):
        for index in range(len(self._rows)):
            yield self[index]

def make_views(case, maximum_work=None):
    meter = _Meter(maximum_work)
    catalog = _Sequence([_View(row['record_id'], row, meter) for row in case['catalog']], meter, 'catalog_visits')
    queries = _Sequence([_View(row['query_id'], row, meter) for row in case['queries']], meter, 'query_visits')
    def snapshot():
        return {'profile': PROFILE, 'counters': dict(meter.values), 'total_work': sum(meter.values.values()),
                'stop_work_exceeded': meter.exceeded}
    return queries, catalog, snapshot
