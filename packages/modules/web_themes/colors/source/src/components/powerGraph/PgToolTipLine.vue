<template>
	<tspan
		v-if="power > 0"
		:x="indent"
		dy="1.3em"
		:class="name ? '' : 'fas'"
		:fill="masterData[cat].color"
	>
		{{ name ? name : masterData[cat].icon }} &nbsp;
	</tspan>
	<tspan text-anchor="end" :x="width - indent">
		<FormatWatt v-if="props.power > 0" :watt="power * 1000" />
	</tspan>
</template>
<script setup lang="ts">
import { masterData } from '@/assets/js/model'
import FormatWatt from '@/components/shared/FormatWatt.vue'
const props = defineProps<{
	cat: string
	name?: string
	indent: number
	power: number
	width: number
}>()
</script>
<style scoped></style>
