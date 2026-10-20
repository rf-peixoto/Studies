#if defined(_WIN32)
# define PUBLIC_API __declspec(dllexport)
#elif defined(__GNUC__) || defined(__clang__)
# define PUBLIC_API __attribute__((visibility("default")))
#else
# define PUBLIC_API
#endif
static int internal_algorithm(int x) { return x * 17 + 42; }
PUBLIC_API int public_function(int x) { return internal_algorithm(x); }
