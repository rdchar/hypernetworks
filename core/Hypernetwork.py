import re

from core.HTConfig import hs_replace_same_vertex
from core.HTErrors import HnInsertError, HnUnknownHsType, HnVertexNoFound
from core.HTRelations import Relations
from core.HTTypes import Types
from core.Hypersimplex import Hypersimplex, NONE, VERTEX, ALPHA, BETA, str_to_node_type
from core.HTMeronymy import *
import logging as log

from utils.HTMatrix import to_matrix, from_matrix


# TODO needs more validation when adding Hs.
#      We get a mess when mixing R naming and assignment names across Hs's.
from utils.HTSearch import get_peaks


class Hypernetwork:
    _counter = 0

    def __init__(self, name="Unnamed"):
        self._hypernetwork = dict()
        self._name = name
        self._types = Types()
        self._relations = Relations()
        # self._counter = 0

    @property
    def counter(self):
        return self._counter

    @property
    def name(self):
        return self._name

    @property
    def hypernetwork(self):
        return self._hypernetwork

    @property
    def relations(self):
        return self._relations

    def load_hs(self, hs):
        self._hypernetwork.update({hs.vertex: hs})

    def add(self, vertex, hstype=NONE, simplex=None, R="", t=-1, M=M_UNKNOWN, N="", f="", partOf=None):
        if vertex in self._hypernetwork:
            # Update an existing node
            temp = self._hypernetwork[vertex]

            if temp.hstype not in [NONE, VERTEX]:
                hstype = temp.hstype

            if temp.simplex and not simplex:
                simplex = temp.simplex[:]

            if temp.R == "" and R != "":
                R = temp.R

            if temp.M == M_UNKNOWN and M > M_UNKNOWN:
                M = temp.M

            if temp.N != "" and N == "":
                N = temp.N

            if temp.f != "" and f == "":
                f = temp.f

            if temp.partOf and not partOf:
                partOf = temp.partOf.copy()

            temp.update(hstype=hstype, simplex=simplex, R=R, t=t, M=M, N=N, f=f, partOf=partOf)
            self._hypernetwork[vertex] = temp

        else:
            # Create a new node
            hs = Hypersimplex(vertex, hstype=hstype, simplex=simplex, R=R, t=t, M=M, N=N, f=f, partOf=partOf)
            self._hypernetwork.update({vertex: hs})

        if R:
            self._relations[R] = None

    def add_hs(self, vertex="", hs=None):
        if vertex:
            vertex = hs.vertex

        self.insert(vertex, hstype=hs.hstype, simplex=hs.simplex, R=hs.R, t=hs.t, M=hs.M, N=hs.N, f=hs.f)

    def delete(self, vertex="", R=""):
        def _delete(_vertex, _parent=""):
            if _parent in self._hypernetwork[_vertex].partOf:
                self._hypernetwork[_vertex].partOf.remove(_parent)

            for _vert in self._hypernetwork[_vertex].simplex:
                if len(self._hypernetwork[_vertex].partOf) == 0:
                    _delete(_vert, _vertex)

            if len(self._hypernetwork[_vertex].partOf) == 0:
                del self._hypernetwork[_vertex]

        # TODO may need more work
        if R:
            vertices = self.search(R=R)
            for vert in vertices:
                _delete(_vertex=vert)

        elif vertex and vertex in self._hypernetwork:
            _delete(_vertex=vertex)

        else:
            raise HnVertexNoFound

        return

    def insert(self, vertex="", hstype=NONE, simplex=None, R="", t=-1, M=M_UNKNOWN, N="", f="", partOf=None):
        def _insert_by_matrix(_simplex):
            if R == self.hypernetwork[vertex].R \
                    or R == "" \
                    or self.hypernetwork[vertex].R == " ":

                mtrx = to_matrix(self, vertex=vertex, R=R)

                if len(mtrx) > 1 and isinstance(mtrx[0], list):
                    mtrx.append(_simplex)
                else:
                    mtrx = [mtrx, _simplex]

                try:
                    from_matrix(self, mtrx, vertex, R)
                    return True

                except:
                    print("ERROR: unable to use the matrix method!")
                    # TODO log that we fall back on the standard processing

                return False
        # END _insert_by_matrix

        if simplex is None:
            simplex = []

        if partOf is None:
            partOf = set()

        if not hs_replace_same_vertex and vertex in self.hypernetwork and R == self.hypernetwork[vertex].R:
            if _insert_by_matrix(simplex):  # TODO need to decide where this is best positioned.
                                            #   Currently it cannot cope with, e.g.
                                            #       face=<<eyes, smile>, round>
                                            #       face=<<eyes, frown>, round>
                return vertex

        # If the simplex of type hsTyoe is found then
        #   replace the new details and all references
        if simplex:
            if vertex or vertex != "":
                search = self.search(hstype=hstype, vertex=vertex, simplex=simplex)
            else:
                search = self.search(hstype=hstype, simplex=simplex)
        else:
            search = self.search(hstype=hstype, vertex=vertex)

        if vertex == "" or not vertex:
            vertex = "hs_{}".format(self._counter)
            self._counter += 1

        if search:
            for v in search:
                if v[:3] == "hs_":
                    self._hypernetwork[v].simplex = [v if x == v else x for x in self._hypernetwork[v].simplex]
                    self._hypernetwork[v].vertex = v
                    self._counter -= 1
                    vertex = v

        else:
            self.add(vertex=vertex, hstype=hstype, simplex=simplex, R=R, t=t, M=M, N=N, f=f,
                     partOf=partOf if isinstance(partOf, set) else {partOf})

            if partOf:
                if isinstance(partOf, str):
                    if partOf in self._hypernetwork:
                        self._hypernetwork[partOf].simplex.append(vertex)
                    else:
                        log.error("insert: partOf error.")
                        raise HnInsertError

            for v in simplex:
                self.add(vertex=v, hstype=VERTEX, partOf={vertex})

        for s in simplex:
            if s in self._hypernetwork:
                self._hypernetwork[s].partOf.add(vertex)

        return vertex

    def parse(self, hypernet):
        class _hypersimplex:
            hs_name = ""
            hs_type = NONE
            hs_simplex = []
            hs_R = ""
            hs_t = -1
            hs_M = M_UNKNOWN
            hs_N = ""
            hs_f = ""
            hs_partOf = set()
            hs_where = ""

        class _relation:
            hs_R = ""
            hs_where = []

        def _parse_hs(_hs):
            for hs_k, hs_v in _hs.items():
                if hs_k == "VAL":
                    _hypersimplex.hs_name = hs_v

                elif hs_k in ["ALPHA", "BETA"]:
                    _hypersimplex.hs_type = str_to_node_type(hs_k)
                    
                    if isinstance(hs_v, str):
                        _hypersimplex.hs_simplex.append(hs_v)
                        
                    else:
                        for v in hs_v:
                            if isinstance(v, list):
                                _hypersimplex.hs_simplex.append(self.parse(v))
                            else:
                                _hypersimplex.hs_simplex.append(v)

                elif hs_k == "R":
                    _relation.hs_R = hs_v
                    _hypersimplex.hs_R = hs_v

                elif hs_k == "t":
                    _hypersimplex.hs_t = hs_v

                elif hs_k == "M":
                    _hypersimplex.hs_M = MERONYMY.index(hs_v)

                elif hs_k == "N":
                    _hypersimplex.hs_N = hs_v

                elif hs_k == "f":
                    _hypersimplex.hs_f = hs_v

                elif hs_k == "TYPE":
                    print("\tTYPE:" + str(hs_v))

                elif hs_k == "TYPED":
                    print("\tTYPED:" + str(hs_v))

                elif hs_k == "WHERE":
                    _relation.hs_where = hs_v

                elif hs_k == "DERIVED":
                    _hypersimplex.hs_where = "DERIVED"

            return _hypersimplex.hs_name

        # End _parse_hs

        def _clear():
            _hypersimplex.hs_name = ""
            _hypersimplex.hs_type = NONE
            _hypersimplex.hs_simplex = []
            _hypersimplex.hs_R = ""
            _hypersimplex.hs_t = -1
            _hypersimplex.hs_M = M_UNKNOWN
            _hypersimplex.hs_N = ""
            _hypersimplex.hs_f = ""

            _relation.hs_R = ""
            _relation.hs_where = []
        # End _clear

        name = ""

        _clear()
        
        print("PARSING ...")
        for hn in hypernet:
            if isinstance(hn, dict):
                _parse_hs(hn)
                print("\tHN 1: " + str(hn))
            else:
                print("\tHN 2: " + str(hn))
                for hs in hn:
                    print("\t\tRECURSE: " + str(hs))
                    _parse_hs(hs)

            if _hypersimplex.hs_type != NONE:
                name = self.insert(vertex=_hypersimplex.hs_name,
                                   hstype=_hypersimplex.hs_type,
                                   simplex=_hypersimplex.hs_simplex,
                                   R=_hypersimplex.hs_R,
                                   t=_hypersimplex.hs_t,
                                   M=_hypersimplex.hs_M,
                                   N=_hypersimplex.hs_N,
                                   f=_hypersimplex.hs_f,
                                   partOf=_hypersimplex.hs_partOf)
                print("\t\t\tADDED: " + name)

                if _relation.hs_where:
                    self.relations[_relation.hs_R] = _relation.hs_where

                _clear()

        return name

    def search(self, vertex="", hstype=NONE, simplex=None, R="", t=-1, M=M_UNKNOWN, N="", partOf=None):
        res = []
        # prev_M = M_UNKNOWN

        for node in self._hypernetwork.values():
            fail = False
            found = False

            if vertex != "" and not fail:
                if node.vertex == vertex:
                    found = True
                else:
                    fail = True

            if simplex and not fail:
                if hstype == VERTEX:
                    if node.simplex == simplex:
                        found = True
                    else:
                        fail = True

                elif hstype == ALPHA:
                    if node.simplex == simplex:
                        found = True
                    else:
                        fail = True

                elif hstype == BETA:
                    if node.simplex \
                            and simplex \
                            and set(node.simplex).intersection(set(simplex)) == set(node.simplex):
                        found = True
                    else:
                        fail = True

                else:
                    fail = True

            # TODO needs more work when we implement full R functionality
            if R and not fail:
                # if node.R == R or re.search(R, node.R):
                if re.search(R, node.R):
                    found = True
                else:
                    fail = True

            # TODO needs more work when we implement full T functionality
            if t >= 0 and not fail:
                if node.t == t:
                    found = True
                else:
                    fail = True

            if N and not fail:
                # if N == node.N or re.match(N, node.N):
                if re.match(N, node.N):
                    found = True
                else:
                    fail = True

            # TODO needs more work when we understand partOf better
            # if partOf:
            #     ...

            if found and not fail:
                res.append(node.vertex)

        return res

    def get_subHn(self, vertex="", hstype=NONE, simplex=None, R="", t=-1, M=M_UNKNOWN, N="", partOf=None):
        class temp:
            Hn = None

        def _get_subHn(_hs):
            if _hs.hstype != VERTEX:
                for v in _hs.simplex:
                    h = self.hypernetwork[v]
                    _get_subHn(h)
                    temp.Hn.add_hs(vertex=v, hs=h)

        temp.Hn = Hypernetwork()
        searchRes = self.search(vertex=vertex, hstype=hstype, simplex=simplex, R=R, t=t, M=M, N=N, partOf=partOf)

        for v in searchRes:
            hs = self._hypernetwork[v]
            temp.Hn.add_hs(vertex=v, hs=hs)
            _get_subHn(hs)

        return temp.Hn

    def get_vertices(self, vertex="", R=""):
        def _get_vertices(_vertex):
            _res = set()

            if self._hypernetwork[_vertex].hstype in [ALPHA, BETA]:
                _res.add(_vertex)
                for v in self._hypernetwork[_vertex].simplex:
                    _res = _res.union(_get_vertices(v))

            elif self._hypernetwork[_vertex].hstype == VERTEX:
                _res.add(self._hypernetwork[_vertex].vertex)

            else:
                log.error("get_vertices: found an unknown Hs Type")
                raise HnUnknownHsType

            return _res

        res = set()

        if R:
            vertices = self.search(R=R)
        elif vertex:
            vertices = self.search(vertex=vertex)
        else:
            vertices = self._hypernetwork.keys()

        for vert in vertices:
            res = res.union(_get_vertices(vert))

        return list(res)

    @property
    def soup(self):
        return list(self.hypernetwork.keys())

    def _dump(self):
        for (k, v) in self._hypernetwork.items():
            print(v._dump())

    def __getitem__(self, item):
        return self._hypernetwork[item]

    def __str__(self):
        res = ""

        for (key, hs) in self._hypernetwork.items():
            res = res + str(hs) + "\n"

        return res

    def test_str(self):
        def _test_str(vertex):
            simplex = self.hypernetwork[vertex]

            _res = (simplex.vertex + "=") if simplex.vertex else ""

            if simplex.hstype == ALPHA:
                _res += "<"
                for v in simplex.simplex:
                    _res += _test_str(v)
                    _res += ", "

                _res += ("; R" + ("_" + simplex.R) if simplex.R != " " else "") if simplex.R else ""
                _res += ("; t_" + str(simplex.t)) if simplex.t > -1 else ""
                _res += ("; M_" + simplex.M) if simplex.M != M_UNKNOWN else ""
                if simplex.N:
                    _res += ">^" + simplex.N + ", "
                else:
                    _res += ">, "

            elif simplex.hstype == BETA:
                _res += "{"
                for v in simplex.simplex:
                    _res += _test_str(v)
                    _res += ", "

                _res += ("; t_" + str(simplex.t)) if simplex.t > -1 else ""
                if simplex.N:
                    _res += "}^" + simplex.N
                else:
                    _res += "}"
    
            elif simplex.hstype == VERTEX:
                return simplex.vertex

            return _res
        # End _test_str

        res = ""
        peaks = get_peaks(self._hypernetwork)

        for peak in peaks:
            res += _test_str(peak)

        # A cheat, but it works
        res = res.replace(", }", "}")
        res = res.replace(", >", ">")
        res = res.replace(", ,", ",")
        res = res.replace(", ;", ";")
        res = res.replace(">, }", ">}")
        res = res.replace(", ,", ",")        

        if res[-2:] == ", ":
            res = res[:-2]

        return res