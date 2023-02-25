#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "testdep.h"

static PyObject *testwheel_get_answer(PyObject *self, PyObject *args)
{
   return PyLong_FromLong(get_answer());
}

static PyMethodDef TestwheelMethods[] = {
    {"get_answer", testwheel_get_answer, METH_NOARGS, NULL},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef testwheelmodule = {
    PyModuleDef_HEAD_INIT,
    "testwheel",
    NULL,
    -1,
    TestwheelMethods
};

PyMODINIT_FUNC PyInit_testwheel(void)
{
    return PyModule_Create(&testwheelmodule);
}
