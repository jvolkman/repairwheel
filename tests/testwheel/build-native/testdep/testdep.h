#ifdef _WIN32
#  define EXPORTED __declspec( dllexport )
#else
#  define EXPORTED extern
#endif

EXPORTED int get_answer();
