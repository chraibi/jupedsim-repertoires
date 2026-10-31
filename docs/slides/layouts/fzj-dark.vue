<template>
  <div class="fzj-dark">
    <div class="band">
      <div class="band-inner">
        <slot />
      </div>
    </div>
  </div>
</template>

<style scoped>
.fzj-dark {
  width: 100%;
  height: 100%;
  background: #fff;
  position: relative;
}
.band {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 91%;
  background: #023d6b;
  color: #fff;
}
.band-inner {
  padding: 1.6rem 3.2rem 0 3.2rem;
}
.band-inner :deep(h1) {
  color: #fff;
  font-weight: 700;
  text-transform: uppercase;
  font-size: 1.5rem;
  margin: 0 0 0.6rem 0;
}
.band-inner :deep(h2),
.band-inner :deep(h3) {
  color: #b4c3da;
  font-weight: 700;
  border: none;
}
.band-inner :deep(h3) {
  font-size: 0.9rem;
  margin: 0.4rem 0 0.2rem 0;
}
.band-inner :deep(p),
.band-inner :deep(li) {
  color: #fff;
  font-size: 0.85rem;
}
.band-inner :deep(ul > li::before) {
  color: #b4c3da;
}
.band-inner :deep(.box) {
  background: rgba(255, 255, 255, 0.08);
  border-left-color: #b4c3da;
  color: #fff;
}
.band-inner :deep(.kicker) {
  color: #b4c3da;
}
.band-inner :deep(.small) {
  color: #b4c3da;
}
.band-inner :deep(code) {
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
}
.band-inner :deep(em) {
  color: #fff;
}
</style>
