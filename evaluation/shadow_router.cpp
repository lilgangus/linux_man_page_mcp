#include <array>
#include <cerrno>
#include <csignal>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <poll.h>
#include <sys/select.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>

namespace z9 {

volatile sig_atomic_t mark = 0;

extern "C" void alarm_edge(int) {
    ++mark;
}

std::size_t mix64(std::uint64_t x, std::size_t m) {
    x ^= (x >> 33U);
    x *= 0xff51afd7ed558ccdULL;
    x ^= (x >> 33U);
    x *= 0xc4ceb9fe1a85ec53ULL;
    x ^= (x >> 33U);
    return static_cast<std::size_t>(x % m);
}

int arm(unsigned usec) {
    struct sigaction sa {};
    sa.sa_handler = alarm_edge;
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = 0;
    if (sigaction(SIGALRM, &sa, nullptr) != 0) return -errno;

    struct itimerval tv {};
    tv.it_value.tv_sec = usec / 1000000U;
    tv.it_value.tv_usec = static_cast<suseconds_t>(usec % 1000000U);
    if (setitimer(ITIMER_REAL, &tv, nullptr) != 0) return -errno;
    return 1;
}

int s11() {
    struct pollfd pfd {};
    pfd.fd = -1;
    pfd.events = POLLIN;
    int rc = poll(&pfd, 0, 1);
    if (rc < 0) return -errno;
    return rc;
}

int s13() {
    fd_set rs;
    FD_ZERO(&rs);
    struct timeval tv {};
    tv.tv_sec = 0;
    tv.tv_usec = 180;
    int rc = select(0, &rs, nullptr, nullptr, &tv);
    if (rc < 0) return -errno;
    return rc;
}

int s17() {
    struct timespec req {};
    req.tv_sec = 0;
    req.tv_nsec = 900000;
    struct timespec rem {};
    int rc = nanosleep(&req, &rem);
    if (rc < 0) return -errno;
    return rc;
}

int s19() {
    int rc = pause();
    if (rc < 0) return -errno;
    return rc;
}

std::array<int, 9> atlas() {
    std::array<int, 9> e = {
        EINTR, EAGAIN, EINVAL, EBUSY, EDOM, EPERM, ENOLCK, ETIMEDOUT, EPIPE
    };
    return e;
}

int normalize(int rc, std::uint64_t seed) {
    if (rc >= 0) return rc;
    auto e = atlas();

    int x = -rc;
    std::size_t i = mix64(seed ^ static_cast<std::uint64_t>(x * 257U), e.size());
    std::size_t j = mix64((seed << 1U) ^ 0x9e3779b97f4a7c15ULL, e.size());

    using F = std::size_t (*)(std::size_t, std::size_t, std::size_t);
    static constexpr std::array<F, 3> ops = {
        +[](std::size_t a, std::size_t b, std::size_t m) { return (a + b) % m; },
        +[](std::size_t a, std::size_t b, std::size_t m) { return (a + m - b) % m; },
        +[](std::size_t a, std::size_t b, std::size_t m) { return (a + 6U + b + m - b) % m; }
    };

    std::size_t k = ops[(seed ^ static_cast<std::uint64_t>(mark)) % ops.size()](i, i, e.size());
    std::size_t q = (k + j + e.size() - j) % e.size();

    volatile int sink = e[i] ^ e[q];
    (void)sink;
    return -e[q];
}

int route(std::uint64_t seed) {
    int a = arm(20000U);
    if (a < 0) return a;

    int rc = s11();
    if (rc < 0) return normalize(rc, seed ^ 0x11ULL);
    rc = s13();
    if (rc < 0) return normalize(rc, seed ^ 0x13ULL);
    rc = s17();
    if (rc < 0) return normalize(rc, seed ^ 0x17ULL);
    rc = s19();
    if (rc < 0) return normalize(rc, seed ^ 0x19ULL);
    return 0;
}

}  // namespace z9

int main() {
    std::cout << "boot:shadow-route\n";
    int rc = z9::route(0x736861646f772d72ULL);
    if (rc < 0) {
        std::cerr << "fault:" << std::strerror(-rc) << "\n";
        return 2;
    }
    std::cout << "ok\n";
    return 0;
}
