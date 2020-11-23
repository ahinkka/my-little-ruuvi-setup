import { h, render } from 'https://unpkg.com/preact@latest?module';
import { useState, useEffect, useLayoutEffect } from 'https://unpkg.com/preact@latest/hooks/dist/hooks.module.js?module';


const serializeHash = (contents) => {
  let keys = Object.keys(contents)
  keys.sort()
  let result = '#'
  let first = true;
  for (const key of keys) {
    let value = contents[key]
    if (first) {
      result += `${key}=${value}`
      first = false
    } else {
      result += `&${key}=${value}`
    }
  }
  return result
}

const parseHash = (hash) => {
  const parts = hash.slice(1).split('&')
  const result = {}
  for (let part of parts) {
    const [key, value] = part.split('=')
    result[key] = value
  }
  return result
}


const minMax = (twoDArray, startDim) => {
  let min = null
  let max = null

  if (startDim === undefined) {
    startDim = 0
  }

  for (let i = startDim; i < twoDArray.length; i++) {
    for (let j = 0; j < twoDArray[i].length; j++) {
      const v = twoDArray[i][j]
      if (min == null || v < min) min = v
      if (max == null || v >= max) max = v
    }
  }

  return { min, max }
}


// https://www.nature.com/articles/nmeth.1618
const colors = [
  [0, 0, 0],
  [230, 159, 0],
  [86, 180, 233],
  [0, 158, 115],
  [240, 228, 66],
  [0, 114, 178],
  [213, 94, 0],
  [204, 121, 167],
].map((triple) => `rgb(${triple[0]}, ${triple[1]}, ${triple[2]})`)


let _plot = undefined
const plot = (element, start, end, measurementType, shouldClearElement, width, height) => {
  const startEpoch = Math.floor(start.getTime() / 1000)
  const endEpoch = Math.floor(end.getTime() / 1000)
  fetch('measurements.json' +
	`?start=${startEpoch}` +
	`&end=${endEpoch}` +
	`&measurementType=${measurementType}`)
    .then((response) => response.json())
    .then((data) => {
      if (shouldClearElement) {
	_plot = undefined
        element.innerHTML = ''
      }

      const periodSecs = endEpoch - startEpoch
      let rollPeriod = 1
      if (periodSecs > 60 * 60) {
	rollPeriod = 5
      } else if (periodSecs > 6 * 60 * 60) {
	rollPeriod = 15
      } else if (periodSecs > 12 * 60 * 60) {
	rollPeriod = 30
      }


      const makeScale = (measurementType, unit) => {
	return {
	  scale: measurementType,
	  values: (self, ticks) => ticks.map(rawValue => rawValue.toFixed(1) + unit)
	}
      }

      const effData = data.data
      let scale
      let hooks = undefined
      if (measurementType == 'temperature') {
	let range = [13.0, 24.0]
	const { min, max } = minMax(effData, 1)
	if (min !== null && max !== null) {
	  if (min < range[0]) range = undefined
	  if (max > range[1]) range = undefined
	}

	scale = {
	  scale: measurementType,
	  auto: range === undefined ? true : false,
	  range: range,
	  values: (self, ticks) => ticks.map(rawValue => rawValue.toFixed(1) + " °C")
	}
      } else if (measurementType == 'humidity') {
	let range = [25.0, 75.0]

	const { min, max } = minMax(effData, 1)
	if (min !== null && max !== null) {
	  if (min < range[0]) range[0] = 0.0
	  if (max > range[1]) range[1] = 100.0
	}

	scale = {
	  scale: measurementType,
	  auto: false,
	  range: range,
	  values: (self, ticks) => ticks.map(rawValue => rawValue.toFixed(1) + " %")
	}
      } else if (measurementType == 'pressure') {
	let range = [980.0, 1025.0]
	for (let i = 1; i < effData.length; i++) {
	  for (let j = 0; j < effData[i].length; j++) {
	    let currentValue = effData[i][j]
	    if (currentValue != null) {
	      const newValue = currentValue / 100.0
	      effData[i][j] = newValue
	      
	      if (range !== undefined && (newValue < range[0] || newValue > range[1])) {
		range = undefined
	      }
	    }
	  }
	}

	scale = {
	  scale: measurementType,
	  auto: range === undefined ? true : false,
	  range: range,
	  values: (self, ticks) => ticks.map(rawValue => rawValue + " hPa")
	}

	hooks = {
	  draw: [(u, si) => {
	    const { ctx } = u
	    const xd = u.data[0]
	    const x0 = u.valToPos(xd[0], 'x', true)
	    const y = u.valToPos(1013.25, scale.scale, true)
	    const x1 = u.valToPos(xd[xd.length - 1], 'x', true)

	    ctx.save()

	    ctx.font = '12px'
	    ctx.fillStyle = "#000000"
	    ctx.textAlign = "left"
	    ctx.textBaseline = "bottom"
	    ctx.fillText("atm", x0, y)

	    ctx.strokeStyle = "#000000"
	    ctx.setLineDash([0])
	    ctx.lineWidth = 2
	    ctx.beginPath()
	    ctx.moveTo(x0, y)
	    ctx.lineTo(x1, y)
	    ctx.stroke()

	    ctx.restore()
	  }]
	}
      } else if (measurementType == 'battery_voltage') {
	scale = makeScale(measurementType, "V")
      } else if (measurementType == 'tx_power') {
	scale = makeScale(measurementType, "dBm")
      }

      // console.log(data)
      // console.log(data.sensors)

      let colorIndex = 0
      const series = data.sensors.reduce((acc, v) => {
	acc.push({
	  label: v,
	  scale: scale.scale,
	  // stroke: "black",
	  stroke: colors[colorIndex],
	  width: 2,
	  dash: [((data.sensors.length - colorIndex) + 1) * 3],
	  spanGaps: true,
	})
	colorIndex++
	return acc
      }, [{}])
      // console.log(series)

      let scales = {}
      scales[scale.scale] = scale
      scale['size'] = 100
      console.log('scales', scales)

      let opts = {
	width: width,
	height: height,
	// height: 600,
	// gutters: { x: 100, y: 100 },
	series: series,
	axes: [{}, scale],
	scales: scales,
	hooks: hooks,
      }

      // console.log("opts", opts)
      // console.log("data", effData)

      if (_plot === undefined) {
	const g = new uPlot(opts, effData, element)
	_plot = g
      } else {
	_plot.setData(effData)
	_plot.setSeries(opts.series)
      }
    })
}


const updateHash = (keys) => {
  const hash = serializeHash(keys)
  if (hash != window.location.hash) {
    let hashLess = window.location.href
    if (window.location.href.includes('#')) {
      hashLess = window.location.href.split('#')[0]
    }
    window.history.pushState(null, null, hashLess + hash)
  }
}


const periodToMillis = (period) => {
  const unit = period.charAt(period.length - 1)
  const amount = period.substring(0, period.length - 1)
  if (unit == 'h') {
    return amount * 60 * 60 * 1000
  } else if (unit == 'd') {
    return amount * 24 * 60 * 60 * 1000
  } else {
    throw new Error(`Unknown unit: ${unit}`)
  }
}


const useWindowSize = () => {
  const [size, setSize] = useState([0, 0])
  useLayoutEffect(() => {
    const updateSize = () => setSize([window.innerWidth, window.innerHeight])
    window.addEventListener('resize', updateSize)
    updateSize()
    return () => window.removeEventListener('resize', updateSize)
  }, [])
  return size
}


const QuickChooser = (props) => {
  const { periodCallback, period } = props
  return h('button', {
    onClick: () => periodCallback(period)
  }, period)
}


const MeasurementTypeDropdown = (props) => {
  const { measurementTypeCallback, measurementType } = props

  return h('select', { onChange: (e) => {
    const select = e.target
    measurementTypeCallback(select.children[select.selectedIndex].value)
  }}, [
    h('option', { value: 'temperature', selected: measurementType == 'temperature' }, 'Temperature'),
    h('option', { value: 'humidity', selected: measurementType == 'humidity' }, 'Humidity'),
    h('option', { value: 'pressure', selected: measurementType == 'pressure' }, 'Pressure'),
    h('option', { value: 'battery_voltage', selected: measurementType == 'battery_voltage' }, 'Battery voltage'),
    h('option', { value: 'tx_power', selected: measurementType == 'tx_power' }, 'TX Power'),
  ])
}


const Header = (props) => {
  const { period, periodCallback, measurementType, measurementTypeCallback } = props
  const millisInHour = 60 * 60 * 1000
  return h('div', { className: 'row row-eq-height', style: { marginTop: '25px' }}, [
    h('h3', { className: 'col col-4' }, 'Measurement browser'),
    h('div', { className: 'col align-middle', style: { lineHeight: 2.5 } },
      [h('div', { className: 'float-right'}, 'Show last')]),
    h(QuickChooser, { className: 'col', periodCallback, period: '1h' }),
    h(QuickChooser, { className: 'col', periodCallback, period: '3h' }),
    h(QuickChooser, { className: 'col', periodCallback, period: '6h' }),
    h(QuickChooser, { className: 'col', periodCallback, period: '12h' }),
    h(QuickChooser, { className: 'col', periodCallback, period: '24h' }),
    h(QuickChooser, { className: 'col', periodCallback, period: '2d' }),
    h(QuickChooser, { className: 'col', periodCallback, period: '3d' }),
    h(QuickChooser, { className: 'col', periodCallback, period: '7d' }),
    h(MeasurementTypeDropdown, { className: 'col', period, measurementType, measurementTypeCallback })
  ])
}


const Chart = (props) => {
  const { start, end, measurementType, innerHeight } = props
  const [width, height] = useWindowSize()

  const [previousMeasurementType, setPreviousMeasurementType] = useState(null)

  useEffect(() => {
    let shouldClearElement = false
    if (measurementType != previousMeasurementType) {
      shouldClearElement = true
    }

    plot((() => document.getElementById('chart'))(), start, end, measurementType, shouldClearElement, width - 350, height - 200)
  }, [start, end, measurementType, width, height])

  return h('div', { className: 'row', style: {
    marginTop: '20px',
    marginRight: '10px',
  }}, [
    h('div', { className: 'col-12', id: 'chart', style: { height: height - 200 }})
  ])
}


const App = (props) => {
  const parsedHash = parseHash(window.location.hash)

  // const [end, setEnd] = useState(parsedHash.end != undefined ? new Date(parseInt(parsedHash.end)) : new Date())
  // const [start, setStart] = useState(
  //   parsedHash.start !== undefined ?
  //     new Date(parseInt(parsedHash.start)) : new Date(end.getTime() - 24 * 60 * 60 * 1000))

  const [period, setPeriod] = useState(parsedHash.period !== undefined ? parsedHash.period : '24h')

  const [measurementType, setMeasurementType] = useState(
    parsedHash.measurementType !== undefined ? parsedHash.measurementType : 'temperature')

  // useEffect(() => {
  //   if (start && end && measurementType) {
  //     updateHash({ start: start.getTime(), end: end.getTime(), measurementType})
  //   }
  // }, [start, end, measurementType])

  useEffect(() => {
    if (period) {
      updateHash({ period, measurementType })
    }
  }, [period, measurementType])

  const now = new Date()
  return h('div', null, [
    h(Header, {
      measurementType,
      measurementTypeCallback: setMeasurementType,
      // timeCallback: (start, end) => {
      // 	setStart(start)
      // 	setEnd(end)
      // }
      period,
      periodCallback: (period) => {
	setPeriod(period)
      }
    }),
    h(Chart, {
      start: new Date(now - periodToMillis(period)),
      end: now,
      measurementType
    }),
  ])
}

window.onload = () => render(h(App), document.getElementById('spa'))
