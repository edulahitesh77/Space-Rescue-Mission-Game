<template>
  <div style="display:none"></div>
</template>
<script>
module.exports = {
  mounted() {
    this._onKeyDown = (e) => {
      const activeTag = document.activeElement ? document.activeElement.tagName.toLowerCase() : "";
      if (activeTag === "input" || activeTag === "textarea") {
        return;
      }
      const k = e.key;
      const code = e.code;
      if (["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(k) ||
          ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(code)) {
        e.preventDefault();
      }
      let keyMapped = null;
      if (k === "ArrowUp" || k === "w" || k === "W" || code === "KeyW" || code === "ArrowUp") {
        keyMapped = "up";
      } else if (k === "ArrowDown" || k === "s" || k === "S" || code === "KeyS" || code === "ArrowDown") {
        keyMapped = "down";
      } else if (k === "ArrowLeft" || k === "a" || k === "A" || code === "KeyA" || code === "ArrowLeft") {
        keyMapped = "left";
      } else if (k === "ArrowRight" || k === "d" || k === "D" || code === "KeyD" || code === "ArrowRight") {
        keyMapped = "right";
      }
      if (keyMapped) {
        this.event_key_press(keyMapped);
      }
    };
    window.addEventListener("keydown", this._onKeyDown);
  },
  destroyed() {
    if (this._onKeyDown) {
      window.removeEventListener("keydown", this._onKeyDown);
    }
  }
};
</script>
