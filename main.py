from pysat.solvers import Glucose3
from math import ceil


class LadderEncoder:
    def __init__(self, n, width):
        self.n = n
        self.width = width
        self.clauses = []
        self.aux_vars = {}
        self.var_counter = n

    def get_new_var(self):
        self.var_counter += 1
        return self.var_counter

    def get_aux_var(self, first, last):
        pair = (first, last)

        if pair in self.aux_vars:
            return self.aux_vars[pair]

        if first == last:
            return first

        new_aux_var = self.get_new_var()
        self.aux_vars[pair] = new_aux_var
        return new_aux_var

    def encode_window(self, window):
        clauses = []

        # First window
        if window == 0:
            lastVar = window * self.width + self.width

            for i in range(self.width - 1, 0, -1):
                var = window * self.width + i
                clauses.append([-var, self.get_aux_var(var, lastVar)])

            for i in range(self.width, 1, -1):
                var = window * self.width + i
                clauses.append([-self.get_aux_var(var, lastVar),
                                self.get_aux_var(var - 1, lastVar)])

            for i in range(1, self.width, 1):
                var = window * self.width + i
                main = self.get_aux_var(var, lastVar)
                sub = self.get_aux_var(var + 1, lastVar)
                clauses.append([var, sub, -main])

            for i in range(1, self.width, 1):
                var = window * self.width + i
                clauses.append([-var, -self.get_aux_var(var + 1, lastVar)])

        # Last window
        elif window == ceil(float(self.n) / self.width) - 1:
            firstVar = window * self.width + 1

            for i in range(2, self.width + 1, 1):
                reverse_var = window * self.width + i
                clauses.append(
                    [-reverse_var, self.get_aux_var(firstVar, reverse_var)])

            for i in range(self.width - 1, 0, -1):
                reverse_var = window * self.width + self.width - i
                clauses.append([-self.get_aux_var(firstVar, reverse_var),
                                self.get_aux_var(firstVar, reverse_var + 1)])

            for i in range(0, self.width - 1, 1):
                var = window * self.width + self.width - i
                main = self.get_aux_var(firstVar, var)
                sub = self.get_aux_var(firstVar, var - 1)
                clauses.append([sub, var, -main])

            for i in range(self.width, 1, -1):
                reverse_var = window * self.width + i
                clauses.append(
                    [-reverse_var, -self.get_aux_var(firstVar, reverse_var - 1)])
        else:
            # Middle windows
            # Upper part
            firstVar = window * self.width + 1

            for i in range(2, self.width + 1, 1):
                reverse_var = window * self.width + i
                clauses.append(
                    [-reverse_var, self.get_aux_var(firstVar, reverse_var)])

            for i in range(self.width - 1, 0, -1):
                reverse_var = window * self.width + self.width - i
                clauses.append([-self.get_aux_var(firstVar, reverse_var),
                                self.get_aux_var(firstVar, reverse_var + 1)])

            for i in range(0, self.width - 1, 1):
                var = window * self.width + self.width - i
                main = self.get_aux_var(firstVar, var)
                sub = self.get_aux_var(firstVar, var - 1)
                clauses.append([sub, var, -main])

            for i in range(self.width, 1, -1):
                reverse_var = window * self.width + i
                clauses.append(
                    [-reverse_var, -self.get_aux_var(firstVar, reverse_var - 1)])

            # Lower part
            lastVar = window * self.width + self.width

            for i in range(self.width - 1, 0, -1):
                var = window * self.width + i
                clauses.append([-var, self.get_aux_var(var, lastVar)])

            for i in range(self.width, 1, -1):
                var = window * self.width + i
                clauses.append([-self.get_aux_var(var, lastVar),
                                self.get_aux_var(var - 1, lastVar)])

            for i in range(1, self.width, 1):
                var = window * self.width + i
                main = self.get_aux_var(var, lastVar)
                sub = self.get_aux_var(var + 1, lastVar)
                clauses.append([var, sub, -main])

            # AMZ
            # for i in range(1, width - 1, 1):
            #     var = window * width + i
            #     clauses.append([-var, get_aux_var(var + 1, lastVar)])
        return clauses

    def glue_window(self, window, isLack):
        clause = []
        for i in range(1, self.width, 1):
            if isLack and i == 1:
                continue
            first_reverse_var = (window + 1) * self.width + 1
            last_var = window * self.width + self.width
            reverse_var = (window + 1) * self.width + i
            var = window * self.width + i + 1

            print("i: ", i, "var: ", var, "last_var: ", last_var, "reverse_var: ",
                  reverse_var, "first_reverse_var: ", first_reverse_var)

            clause.append([
                -self.get_aux_var(var, last_var),
                -self.get_aux_var(first_reverse_var, reverse_var)
            ])
        return clause

    def generate_clauses(self, isLack):
        clauses = []
        for gw in range(0, ceil(float(self.n) / self.width)):
            clauses.extend(self.encode_window(gw))

        for gw in range(0, ceil(float(self.n) / self.width) - 1):
            clauses.extend(self.glue_window(gw, isLack))

        return clauses

    def solve(self, isLack):
        clauses = self.generate_clauses(isLack)
        solver = Glucose3()

        for clause in clauses:
            solver.add_clause(clause)

        # print( solver.solve())
        print(clauses)


encoder = LadderEncoder(16, 4)
encoder.solve(1)
