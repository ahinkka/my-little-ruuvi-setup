import { h, render } from 'https://unpkg.com/preact@latest?module';
import { useState, useEffect, useLayoutEffect, useRef } from 'https://unpkg.com/preact@latest/hooks/dist/hooks.module.js?module';

const LIST_HASH_VALUES = 'selectedSensors'
const serializeHash = (contents) => {
  let keys = Object.keys(contents)
  keys.sort()
  let result = '#'
  let first = true;
  for (const key of keys) {
    let value = contents[key]
    if (!value) {
      continue
    } else if (first) {
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
    if (LIST_HASH_VALUES.includes(key)) {
      if (value === 'null') {
	result[key] = null
      } else if (value === '') {
	result[key] = []
      } else {
	result[key] = value?.split(',') ?? []
      }
    } else {
      result[key] = value
    }
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


const tooltipPlugin = (opts = {}) => {
  let tooltip;

  const fmtDate = uPlot.fmtDate("{YYYY}-{MM}-{DD} {HH}:{mm}");

  function init(u) {
    tooltip = document.createElement("div");
    tooltip.className = "u-tooltip";
    tooltip.style.pointerEvents = "none";
    tooltip.style.position = "absolute";
    tooltip.style.background = "rgba(255, 255, 255, 0.95)";
    tooltip.style.border = "2px solid #ccc";
    tooltip.style.borderRadius = "4px";
    tooltip.style.padding = "8px";
    tooltip.style.fontSize = "12px";
    tooltip.style.fontFamily = "sans-serif";
    tooltip.style.boxShadow = "0 2px 4px rgba(0,0,0,0.1)";
    tooltip.style.zIndex = "100";
    tooltip.style.display = "none";
    tooltip.style.whiteSpace = "pre";
    u.over.appendChild(tooltip);

    u.over.addEventListener("mouseleave", () => {
      tooltip.style.display = "none";
    });

    u.over.addEventListener("mouseenter", () => {
      tooltip.style.display = "block";
    });
  }

  function setCursor(u) {
    const { left, top, idx } = u.cursor;

    if (idx == null || left < 0 || top < 0) {
      tooltip.style.display = "none";
      return;
    }

    // Calculate distances for all series
    const distances = [];
    for (let i = 1; i < u.series.length; i++) {
      const s = u.series[i];
      if (!s.show) continue;
      const val = u.data[i][idx];
      if (val == null) continue;

      const yPos = u.valToPos(val, s.scale);
      const dist = Math.abs(top - yPos);
      distances.push({ idx: i, dist, val, label: s.label, stroke: s.stroke });
    }

    // Sort by distance, take top N based on mode
    distances.sort((a, b) => a.dist - b.dist);
    const count = opts.summaries ? 3 : 1;
    const closest = distances.slice(0, count);

    if (closest.length === 0) {
      tooltip.style.display = "none";
      return;
    }

    // Build tooltip content
    const timestamp = u.data[0][idx];
    const dateStr = fmtDate(new Date(timestamp * 1000));
    let lines = [dateStr];
    for (const c of closest) {
      const text = `${c.label}: ${c.val.toFixed(2)}`;
      const isMainSeries = !c.label.startsWith("Low ") && !c.label.startsWith("High ");
      lines.push(isMainSeries ? `<b>${text}</b>` : text);
    }
    tooltip.innerHTML = lines.join("<br>");
    tooltip.style.borderColor = closest[0].stroke;

    // Position tooltip near cursor but keep it on screen
    const plotWidth = u.over.clientWidth;
    const plotHeight = u.over.clientHeight;
    const tooltipWidth = tooltip.offsetWidth;
    const tooltipHeight = tooltip.offsetHeight;

    let tooltipLeft = left + 15;
    let tooltipTop = top + 15;

    // Flip to left side if tooltip would go off right edge
    if (tooltipLeft + tooltipWidth > plotWidth) {
      tooltipLeft = left - tooltipWidth - 15;
    }

    // Flip to above if tooltip would go off bottom edge
    if (tooltipTop + tooltipHeight > plotHeight) {
      tooltipTop = top - tooltipHeight - 15;
    }

    tooltip.style.left = tooltipLeft + "px";
    tooltip.style.top = tooltipTop + "px";
    tooltip.style.display = "block";
  }

  return {
    hooks: {
      init,
      setCursor,
    },
  };
};


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
  const { measurementTypeCallback, measurementType, dataSource } = props

  const allOptions = [
    { value: 'temperature', label: 'Temperature' },
    { value: 'humidity', label: 'Humidity' },
    { value: 'pressure', label: 'Pressure' },
    { value: 'battery_voltage', label: 'Battery voltage' },
    { value: 'tx_power', label: 'TX Power' },
  ]

  const summaryOptions = [
    { value: 'temperature', label: 'Temperature' },
    { value: 'humidity', label: 'Humidity' },
  ]

  const options = dataSource === 'summaries' ? summaryOptions : allOptions

  return h('select', { onChange: (e) => {
    const select = e.target
    measurementTypeCallback(select.children[select.selectedIndex].value)
  }}, options.map(opt =>
    h('option', { value: opt.value, selected: measurementType == opt.value }, opt.label)
  ))
}


const DataSourceDropdown = (props) => {
  const { dataSourceCallback, dataSource } = props

  return h('select', { onChange: (e) => {
    dataSourceCallback(e.target.value)
  }}, [
    h('option', { value: 'measurements', selected: dataSource == 'measurements' }, 'Measurements'),
    h('option', { value: 'summaries', selected: dataSource == 'summaries' }, 'Summaries'),
  ])
}


const SensorSelector = (props) => {
  const { sensorIdsWithData, sensors, selectedSensors, setSelectedSensors } = props
  const sensorIds = Object.keys(sensors)
  const allSensorIds = Array.from(new Set([...sensorIdsWithData, ...sensorIds])).sort()

  if (allSensorIds.length === 0) {
    return []
  }

  return allSensorIds.flatMap((sensorId) => {
    const sensorName = sensors[sensorId]?.name ?? sensorId
    const checkBoxElementId = `sensor-checkbox-${sensorId}`
    return [
      h('label', { 'for': checkBoxElementId }, [sensorName]),
      h('input', {
	type: 'checkbox',
	name: sensorName,
	id: checkBoxElementId,
	checked: !selectedSensors || selectedSensors.includes(sensorId),
	onClick: () => {
	  if (selectedSensors && selectedSensors.includes(sensorId)) {
	    setSelectedSensors(selectedSensors.filter((sid) => sid !== sensorId))
	  } else if (!selectedSensors) {
	    setSelectedSensors(allSensorIds.filter((sid) => sid !== sensorId))
	  } else {
	    setSelectedSensors([...(selectedSensors ?? []), sensorId])
	  }
	}
      })
    ]
  })
}


const Header = (props) => h('header', {}, [
  h('h3', { style: { display: 'inline' } }, 'Measurement browser')
])


const Nav = (props) => {
  const {
    period, periodCallback,
    measurementType, measurementTypeCallback,
    dataSource, dataSourceCallback,
    sensorIdsWithData, sensors, selectedSensors, setSelectedSensors
  } = props
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
      h(DataSourceDropdown, {
        dataSource,
        dataSourceCallback
      })
    ]),
    h('fieldset', {}, [
      h(MeasurementTypeDropdown, {
        className: '',
        period,
        measurementType,
        measurementTypeCallback,
        dataSource
      })
    ])
    // h('fieldset', {}, [
    //   h(SensorSelector, { sensorIdsWithData, sensors, selectedSensors, setSelectedSensors })
    // ])
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
    plugins: [
      tooltipPlugin({ summaries }),
    ],
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


const Chart = (props) => {
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


const useSensors = () => {
  const [sensors, setSensors] = useState({})

  useEffect(() => {
    console.time('fetch sensors.json()')
    fetch('sensors.json')
      .then((response) => response.json())
      .then((data) => {
	console.timeEnd('fetch sensors.json()')
	setSensors(data)
      })
  }, [])

  return sensors
}


const useMeasurementsOrSummaries = (props) => {
  const { period, measurementType, dataSource } = props
  const [data, setData] = useState(null)

  useEffect(() => {
    const end = new Date()
    const start = new Date(end - periodToMillis(period))

    const startEpoch = Math.floor(start.getTime() / 1000)
    const endEpoch = Math.floor(end.getTime() / 1000)
    const endpoint = dataSource === 'summaries' ? 'summaries.json' : 'measurements.json'

    console.time(`fetch ${endpoint}()`)
    fetch(endpoint +
          `?start=${startEpoch}` +
          `&end=${endEpoch}` +
          `&measurementType=${measurementType}`)
      .then((response) => response.json())
      .then((data) => {
	console.timeEnd(`fetch ${endpoint}()`)
	data.measurementType = measurementType
	setData(data)
      })
  }, [period, measurementType, dataSource])

  return data
}


const App = (props) => {
  const sensors = useSensors()
  const parsedHash = parseHash(window.location.hash)
  const [selectedSensors, setSelectedSensors] = useState(
    Object.keys(parsedHash).includes('selectedSensors')
      ? parsedHash.selectedSensors
      : null
  )

  // const [end, setEnd] = useState(parsedHash.end != undefined ? new Date(parseInt(parsedHash.end)) : new Date())
  // const [start, setStart] = useState(
  //   parsedHash.start !== undefined ?
  //     new Date(parseInt(parsedHash.start)) : new Date(end.getTime() - 24 * 60 * 60 * 1000))

  const [period, setPeriod] = useState(parsedHash.period !== undefined ? parsedHash.period : '24h')

  const [measurementType, setMeasurementType] = useState(
    parsedHash.measurementType !== undefined ? parsedHash.measurementType : 'temperature')

  const [dataSource, setDataSource] = useState(
    parsedHash.dataSource !== undefined ? parsedHash.dataSource : 'summaries')

  // useEffect(() => {
  //   if (start && end && measurementType) {
  //     updateHash({ start: start.getTime(), end: end.getTime(), measurementType})
  //   }
  // }, [start, end, measurementType])

  useEffect(() => {
    if (period) {
      updateHash({ period, measurementType, dataSource, selectedSensors })
    }
  }, [period, measurementType, dataSource, selectedSensors])

  // Reset measurement type if switching to summaries and current type is not supported
  useEffect(() => {
    if (dataSource === 'summaries' && measurementType !== 'temperature' && measurementType !== 'humidity') {
      setMeasurementType('temperature')
    }
  }, [dataSource])

  // TODO: parameterize fetching after we have a proper "all sensors" endpoint
  const measurementOrSummaryData = useMeasurementsOrSummaries({ period, measurementType, dataSource })

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
      },
      dataSource,
      dataSourceCallback: setDataSource,
      sensorIdsWithData: measurementOrSummaryData?.sensors ?? [],
      sensors,
      selectedSensors,
      setSelectedSensors
    }),
    h(Chart, { data: measurementOrSummaryData, sensors })
  ])
}

window.onload = () => render(h(App), document.getElementById('content'))
