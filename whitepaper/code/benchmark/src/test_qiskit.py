# Copyright 2023 Huawei Technologies Co., Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ============================================================================
"""Benchmark qiskit."""
from functools import partial, reduce
from operator import xor, add
import os
import re
import pytest
import json
import numpy as np
from scipy.optimize import minimize

from qiskit import QuantumCircuit
from qiskit.circuit import ParameterVector
from qiskit_aer import AerSimulator
from qiskit.quantum_info import SparsePauliOp, Statevector
from qiskit.opflow.gradients import Gradient
from qiskit.opflow import I, X, Z, StateFn
import qiskit.circuit.library as G

current_path = os.path.dirname(os.path.abspath(__file__))
data_path = os.path.join(current_path, os.path.abspath("../data"))


def get_task_file(task: str):
    """Get all data file name."""
    all_path = []
    for file_name in os.listdir(data_path):
        if file_name.startswith(task):
            full_path = os.path.join(data_path, file_name)
            all_path.append(full_path)
    return all_path


def convert_back_to_qiskit_circ(str_circ, n_qubits):
    """Convert str gate back to Qiskit circuit."""
    circ = QuantumCircuit(n_qubits)
    for str_g in str_circ:
        name = str_g["name"]
        obj = str_g["obj"]
        ctrl = str_g["ctrl"]
        val = str_g.get("val", 0)
        if name in ["y", "x", "z", "h"]:
            if not ctrl:
                getattr(circ, name)(obj[0])
                continue
            if len(ctrl) == 1:
                getattr(circ, f"c{name}")(ctrl[0], obj[0])
                continue
        if name == "ps":
            if not ctrl:
                circ.p(val, obj[0])
                continue
            if len(ctrl) == 1:
                circ.append(G.CPhaseGate(val), ctrl + obj)
                continue
        if name in ["rx", "ry", "rz"]:
            if not ctrl:
                getattr(circ, name)(val, obj[0])
                continue
            if len(ctrl) == 1:
                circ.append(getattr(G, f"C{name.upper()}Gate")(val), ctrl + obj)
                continue
        if name == "swap":
            if not ctrl:
                circ.swap(obj[0], obj[1])
                continue
        if name in ["rxx", "ryy", "rzz"]:
            if not ctrl:
                getattr(circ, name)(val, obj[0], obj[1])
                continue
        if name in ['s', 't']:
            if not ctrl:
                circ.append(getattr(G, f"{name.upper()}Gate")(), obj)
                continue
        if name in ['sdag', 'tdag']:
            if not ctrl:
                circ.append(getattr(G, f"{name[0].upper()}dgGate")(), obj)
                continue
        raise ValueError(f"gate not implement: {name}({obj}, {ctrl})")
    return circ

def run_sim(sim, circ):
    sim.run(circ).result().get_statevector()

# Section One
# Benchmark random circuit
# Available pytest mark: random_circuit, qiskit

random_circuit_data_path = get_task_file("random_circuit")
random_circuit_data_path.sort()
random_circuit_data_path = random_circuit_data_path[:24]


@pytest.mark.random_circuit
@pytest.mark.qiskit
@pytest.mark.parametrize("file_name", random_circuit_data_path)
@pytest.mark.skip("Gate not supported.")
def test_qiskit_random_circuit(benchmark, file_name):
    n_qubits = int(re.search(r"qubit_\d+", file_name).group().split("_")[-1])
    with open(file_name, "r", encoding="utf-8") as f:
        str_circ = json.load(f)
    circ = convert_back_to_qiskit_circ(str_circ, n_qubits)
    circ.save_statevector()
    sim = AerSimulator(method="statevector", device="CPU", fusion_enable=False)
    benchmark(run_sim, sim, circ)

# Section Two
# Benchmark simple gate set circuit
# Available pytest mark: simple_circuit, qiskit

simple_circuit_data_path = get_task_file("simple_circuit")
simple_circuit_data_path.sort()
simple_circuit_data_path = simple_circuit_data_path[:24]


@pytest.mark.simple_circuit
@pytest.mark.qiskit
@pytest.mark.parametrize("file_name", simple_circuit_data_path)
def test_qiskit_simple_circuit(benchmark, file_name):
    n_qubits = int(re.search(r"qubit_\d+", file_name).group().split("_")[-1])
    with open(file_name, "r", encoding="utf-8") as f:
        str_circ = json.load(f)
    circ = convert_back_to_qiskit_circ(str_circ, n_qubits)
    circ.save_statevector()
    sim = AerSimulator(method="statevector", device="CPU", fusion_enable=False)
    benchmark(run_sim, sim, circ)

# Section Three
# Benchmark four regular qaoa
# Available pytest mark: regular_4, qiskit

regular_4_data_path = get_task_file("regular_4")
regular_4_data_path.sort()
regular_4_data_path = regular_4_data_path[:3]


def qaoa_circuit(n_qubits, edges):
    circ = QuantumCircuit(n_qubits)
    params = ParameterVector("theta", length=len(edges) + n_qubits)
    for i in range(n_qubits):
        circ.h(i)
    for idx, (i, j) in enumerate(edges):
        circ.rzz(params[idx], i, j)
    for i in range(n_qubits):
        circ.rx(params[i+len(edges)], i)
    return circ, params

def fun_and_grad(weights, op, grad, params):
    value_dict = {params: weights}
    exp_result = op.assign_parameters(value_dict).eval()
    grad_result = grad.assign_parameters(value_dict).eval()
    with open('res', '+a') as f:
        f.writelines(str(np.array(exp_result).real)+'\n')
    return np.real(exp_result), np.real(grad_result)

def benchmark_qaoa(weights, op, grad, params):
    res = minimize(fun_and_grad, x0=weights, args=(op, grad, params), jac=True, method='bfgs')

@pytest.mark.regular_4
@pytest.mark.qiskit
@pytest.mark.parametrize("file_name", regular_4_data_path)
@pytest.mark.skip("Too Long")
def test_qiskit_regular_4(benchmark, file_name):
    n_qubits = int(re.search(r"qubit_\d+", file_name).group().split("_")[-1])
    with open(file_name, "r", encoding="utf-8") as f:
        edges = [tuple(i) for i in json.load(f)]

    hams = []
    for i, j in edges:
        o = [I for i in range(n_qubits)]
        o[i], o[j] = Z, Z
        hams.append(reduce(xor, o))
    hams = reduce(add, hams)
    circ, params = qaoa_circuit(n_qubits, edges)
    op = ~StateFn(hams) @ StateFn(circ)
    grad = Gradient().convert(operator=op, params=params)
    weights = np.random.uniform(size=len(edges)+n_qubits)
    benchmark(benchmark_qaoa, weights, op, grad, params)