#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "testlib.h"

static PyObject *simpleext_get_answer(PyObject *self, PyObject *args)
{
   return PyLong_FromLong(get_answer());
}

static PyMethodDef SimpleExtMethods[] = {
    {"get_answer", simpleext_get_answer, METH_NOARGS, NULL},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef simpleextmodule = {
    PyModuleDef_HEAD_INIT,
    "simpleext",
    NULL,
    -1,
    SimpleExtMethods
};

PyMODINIT_FUNC PyInit_simpleext(void)
{
    return PyModule_Create(&simpleextmodule);
}
