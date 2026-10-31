<template>
  <div class="fzj-footer">
    <div v-if="!['fzj-cover', 'fzj-section', 'fzj-dark'].includes($nav.currentLayout)" class="meta">
      30 October 2026 &nbsp;&nbsp; {{ $nav.currentPage }}
    </div>
    <img class="logo" src="/juelich_logo.png" alt="Forschungszentrum Jülich" />
  </div>
</template>

<style scoped>
.fzj-footer {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 9%;
  padding: 0 1.8rem 0 1.4rem;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  pointer-events: none;
  z-index: 10;
}
.meta {
  color: #023d6b;
  font-size: 0.55rem;
  position: absolute;
  left: 40%;
}
.logo {
  height: 1.7rem;
}
</style>
