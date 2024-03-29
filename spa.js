import { h, render } from 'https://unpkg.com/preact@latest?module';
import { useState, useEffect, useLayoutEffect, useRef } from 'https://unpkg.com/preact@latest/hooks/dist/hooks.module.js?module';


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


const scaleFromMeasurementTypeAndUnit = (measurementType, unit) => {
  return {
    scale: measurementType,
    values: (self, ticks) => ticks.map(rawValue => rawValue.toFixed(1) + unit)
  }
}


const scaleForTemperature = (values) => {
  let range = [2.0, 24.0]
  const { min, max } = minMax(values, 1)
  if (min !== null && max !== null) {
    if (min < range[0]) range = undefined
    else if (max > range[1]) range = undefined
  }

  return {
    scale: 'temperature',
    auto: range === undefined ? true : false,
    range: range,
    values: (self, ticks) => ticks.map(rawValue => rawValue.toFixed(1) + " °C")
  }
}


const scaleForHumidity = (values) => {
  let range = [15.0, 75.0]

  const { min, max } = minMax(values, 1)
  if (min !== null && max !== null) {
    if (min < range[0]) range[0] = 0.0
    if (max > range[1]) range[1] = 100.0
  }

  return {
    scale: 'humidity',
    auto: false,
    range: range,
    values: (self, ticks) => ticks.map(rawValue => rawValue.toFixed(1) + " %")
  }
}


const scaleForPressure = (values) => {
  let range = [980.0, 1035.0]
  for (let i = 1; i < values.length; i++) {
    for (let j = 0; j < values[i].length; j++) {
      let currentValue = values[i][j]
      if (currentValue != null) {
        const newValue = currentValue / 100.0
        values[i][j] = newValue

        if (range !== undefined && (newValue < range[0] || newValue > range[1])) {
          console.info(`Pressure beyond normal ${range} range, defaulting to auto range`)
          range = undefined
        }
      }
    }
  }

  return {
    scale: 'pressure',
    auto: range === undefined ? true : false,
    range: range,
    values: (self, ticks) => ticks.map(rawValue => rawValue + " hPa")
  }
}


const pressureHooksFromScaleName = (scaleName) => {
  return {
    draw: [(u, si) => {
      const { ctx } = u
      const xd = u.data[0]
      const x0 = u.valToPos(xd[0], 'x', true)
      const y = u.valToPos(1013.25, scaleName, true)
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
}


const seriesAndBandsFromSensorsAndScaleName = (sensors, sensorConfig, summaries, scaleName) => {
  let sensorIndex = 0
  return sensors.reduce((acc, v) => {
    const [seriesAcc, bandsAcc] = acc
    const sensorName = sensorConfig[v] ? sensorConfig[v].name : v

    if (summaries === true) {
      seriesAcc.push({
	label: `Low ${sensorName}`,
	scale: scaleName,
	stroke: colors[sensorIndex],
	width: 0.1,
      })

      seriesAcc.push({
	label: `High ${sensorName}`,
	scale: scaleName,
	stroke: colors[sensorIndex],
	width: 0.1,
      })

      const lowIndex = 1 + sensorIndex * 3
      const highIndex = 1 + sensorIndex * 3 + 1
      bandsAcc.push({
	show: true,
	series: [highIndex, lowIndex],
	fill: "rgba(0, 0, 0, .07)",
      })
    }

    seriesAcc.push({
      label: sensorName,
      scale: scaleName,
      // stroke: "black",
      stroke: colors[sensorIndex],
      width: 2,
      dash: [((sensors.length - sensorIndex) + 1) * 3],
      spanGaps: true,
    })
    sensorIndex++
    return [seriesAcc, bandsAcc]
  }, [[{}], []])
}


const scaleAndHooksForMeasurementTypeAndValues = (measurementType, values) => {
  if (measurementType == 'temperature') {
    return [scaleForTemperature(values), null]
  } else if (measurementType == 'humidity') {
    return [scaleForHumidity(values), null]
  } else if (measurementType == 'pressure') {
    const scale = scaleForPressure(values)
    return [scale, pressureHooksFromScaleName(scale.scale)]
  } else if (measurementType == 'battery_voltage') {
    return [scaleFromMeasurementTypeAndUnit(measurementType, "V"), null]
  } else if (measurementType == 'tx_power') {
    return [scaleFromMeasurementTypeAndUnit(measurementType, "dBm"), null]
  }
  console.assert(false, `unhandled measurement type: "${measurementType}"?`)
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


const Header = (props) => h('header', {}, [
  h('h3', { style: { display: 'inline' } }, 'Measurement browser')
])


const Nav = (props) => {
  const { period, periodCallback, measurementType, measurementTypeCallback } = props
  const millisInHour = 60 * 60 * 1000
  return h('nav', {}, [
    h('fieldset', {}, [
      h('legend', {}, 'Show last'),
      h(QuickChooser, { className: '', periodCallback, period: '1h' }),
      h(QuickChooser, { className: '', periodCallback, period: '6h' }),
      h(QuickChooser, { className: '', periodCallback, period: '12h' }),
      h(QuickChooser, { className: '', periodCallback, period: '24h' }),
      h(QuickChooser, { className: '', periodCallback, period: '2d' }),
      h(QuickChooser, { className: '', periodCallback, period: '7d' }),
      h(QuickChooser, { className: '', periodCallback, period: '30d' }),
      h(QuickChooser, { className: '', periodCallback, period: '90d' }),
      h(QuickChooser, { className: '', periodCallback, period: '180d' }),
      h(QuickChooser, { className: '', periodCallback, period: '365d' }),
    ]),
    h('fieldset', {}, [
      h(MeasurementTypeDropdown, {
        className: '',
        period,
        measurementType,
        measurementTypeCallback
      })
    ])
  ])
}


const plot = (element, measurementType, summaries, data, sensorConfig, shouldClearElement, width, height) => {
  const effData = data.data
  let [scale, hooks] = scaleAndHooksForMeasurementTypeAndValues(measurementType, effData)
  console.assert(scale, 'no scale')

  const [series, bands] = seriesAndBandsFromSensorsAndScaleName(data.sensors, sensorConfig, summaries, scale.scale)
  console.assert(series, 'no series')
  console.assert(bands, 'no bands')

  let scales = {}
  scales[scale.scale] = scale
  scale['size'] = 100 // makes the left side not clip the scale values

  let opts = {
    width: width,
    height: height,
    series: series,
    bands: bands,
    axes: [{}, scale],
    scales: scales,
    hooks: hooks,
  }

  // console.log('effData.length', effData.length)
  // console.log('series', series)
  // console.log('bands', bands)

  // This is kinda crude, we might be able to use the same plot object. Just
  // couldn't make it work this time.
  element.innerHTML = ''
  // console.time('new uPlot')
  const g = new uPlot(opts, effData, element)
  // console.timeEnd('new uPlot')
}


const ChartWithData = (props) => {
  const { data, sensors } = props
  const [previousMeasurementType, setPreviousMeasurementType] = useState(null)
  const element = useRef(null)
  const [windowWidth, windowHeight] = useWindowSize()

  let [width, height] = [null, null]
  if (element.current) {
    const boundingRect = element.current.getBoundingClientRect()
    width = Math.floor(boundingRect.width)
    const maxHeight = (windowHeight - 100)
    height = width * 0.75
    if (height > maxHeight) height = maxHeight
  }

  useEffect(() => {
    if (element.current && data) {
      element.current.style.width = width;
      element.current.style.height = height;
    }
  }, [width, height])

  useEffect(() => {
    if (element.current && data) {
      plot(
        element.current,
        data.measurementType,
        data.summaries,
        data,
        sensors,
        data.measurementType == previousMeasurementType,
        width,
        height
      )
    } else {
      // console.log('no current element')
    }
  }, [data, width, height])

  return h('div', {
      ref: element,
      id: 'chart',
      style: {
        width: width,
        height: height
      }
  }, [])
}


const Chart = (props) => {
  const { start, end, measurementType } = props
  const [sensors, setSensors] = useState({})
  const [data, setData] = useState(null)

  useEffect(() => {
    console.time('fetch sensors.json()')
    fetch('sensors.json')
      .then((response) => response.json())
      .then((data) => {
	console.timeEnd('fetch sensors.json()')
	setSensors(data)
      })
  }, [])

  useEffect(() => {
    const startEpoch = Math.floor(start.getTime() / 1000)
    const endEpoch = Math.floor(end.getTime() / 1000)

    console.time('fetch measurements.json()')
    fetch('measurements.json' +
          `?start=${startEpoch}` +
          `&end=${endEpoch}` +
          `&measurementType=${measurementType}`)
      .then((response) => response.json())
      .then((data) => {
	console.timeEnd('fetch measurements.json()')
	data.measurementType = measurementType
	setData(data)
      })
  }, [start, end, measurementType])

  return h('div', {}, [
    h(ChartWithData, { data, sensors }),
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
    h(Header),
    h(Nav, {
      measurementType,
      measurementTypeCallback: setMeasurementType,
      // timeCallback: (start, end) => {
      //        setStart(start)
      //        setEnd(end)
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

window.onload = () => render(h(App), document.getElementById('content'))
