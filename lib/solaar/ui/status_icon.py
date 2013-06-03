#
#
#

from __future__ import absolute_import, division, print_function, unicode_literals

from logging import getLogger, DEBUG as _DEBUG
_log = getLogger('solaar.ui.tray')
del getLogger

from gi.repository import Gtk, GLib

from solaar import NAME
from . import action as _action, icons as _icons
from logitech.unifying_receiver import status as _status

_MENU_ICON_SIZE = Gtk.IconSize.LARGE_TOOLBAR

#
#
#

def _create_common(icon, menu_activate_callback):
	icon._devices_info = []

	icon.set_title(NAME)

	icon._menu_activate_callback = menu_activate_callback
	icon._menu = menu = Gtk.Menu()

	no_receiver = Gtk.MenuItem.new_with_label('No receiver found')
	no_receiver.set_sensitive(False)
	menu.append(no_receiver)

	# per-device menu entries will be generated as-needed
	menu.append(Gtk.SeparatorMenuItem.new())
	menu.append(_action.about.create_menu_item())
	menu.append(_action.make('application-exit', 'Quit', Gtk.main_quit).create_menu_item())
	menu.show_all()


try:
	from gi.repository import AppIndicator3

	_log.debug("using AppIndicator3")

	# def _scroll(ind, delta, direction):
	# 	if _log.isEnabledFor(_DEBUG):
	# 		_log.debug("scroll delta %s direction %s", delta, direction)

	def create(activate_callback, menu_activate_callback):
		assert activate_callback
		assert menu_activate_callback

		ind = AppIndicator3.Indicator.new(
						'indicator-solaar',
						_icons.TRAY_INIT,
						AppIndicator3.IndicatorCategory.HARDWARE)
		ind.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
		ind.set_label(NAME, NAME)

		# theme_paths = Gtk.IconTheme.get_default().get_search_path()
		# ind.set_icon_theme_path(':'.join(theme_paths))

		# ind.set_icon(_icons.TRAY_INIT)
		ind.set_attention_icon(_icons.TRAY_ATTENTION)

		_create_common(ind, menu_activate_callback)
		ind.set_menu(ind._menu)

		# ind.connect('scroll-event', _scroll)

		return ind


	# def destroy(ind):
	# 	ind.set_status(AppIndicator3.IndicatorStatus.PASSIVE)


	def _update_icon(ind, icon_name, tooltip):
		icon_file = _icons.icon_file(icon_name, 32)
		ind.set_icon(icon_file)
		# ind.set_icon_full(icon_name, tooltip)


	def attention(ind):
		if ind.get_status != AppIndicator3.IndicatorStatus.ATTENTION:
			ind.set_status(AppIndicator3.IndicatorStatus.ATTENTION)
			GLib.timeout_add(10 * 1000, ind.set_status, AppIndicator3.IndicatorStatus.ACTIVE)

except ImportError:

	_log.debug("using StatusIcon")

	def create(activate_callback, menu_activate_callback):
		assert activate_callback
		assert menu_activate_callback

		icon = Gtk.StatusIcon.new_from_icon_name(_icons.TRAY_INIT)
		icon.set_name(NAME)
		icon.set_tooltip_text(NAME)
		icon.connect('activate', activate_callback)

		_create_common(icon, menu_activate_callback)
		icon.connect('popup_menu',
						lambda icon, button, time, menu:
							icon._menu.popup(None, None, icon.position_menu, icon, button, time),
						icon._menu)

		return icon


	# def destroy(icon):
	# 	icon.set_visible(False)


	def _update_icon(icon, icon_name, tooltip):
		icon.set_from_icon_name(icon_name)
		icon.set_tooltip_markup(tooltip)


	_icon_after_attention = None

	def _blink(icon, count):
		global _icon_after_attention
		if count % 2:
			icon.set_from_icon_name(_icons.TRAY_ATTENTION)
		else:
			icon.set_from_icon_name(_icon_after_attention)

		if count > 0:
			GLib.timeout_add(1000, _blink, icon, count - 1)

	def attention(icon):
		global _icon_after_attention
		if _icon_after_attention is None:
			_icon_after_attention = icon.get_icon_name()
			GLib.idle_add(_blink, icon, 9)

#
#
#

def _generate_tooltip_lines(devices_info):
	yield '<b>%s</b>' % NAME
	yield ''

	for _, serial, name, _, status in devices_info:
		if serial is None:  # receiver
			continue

		yield '<b>%s</b>' % name

		p = str(status)
		if p:  # does it have any properties to print?
			if status:
				yield '\t%s' % p
			else:
				yield '\t%s <small>(inactive)</small>' % p
		else:
			if status:
				yield '\t<small>no status</small>'
			else:
				yield '\t<small>(inactive)</small>'
		yield ''


def _generate_icon_name(icon):
	if not icon._devices_info:
		return _icons.TRAY_INIT

	battery_status = None
	battery_level = 1000

	for _, serial, name, _, status in icon._devices_info:
		if serial is None: # is receiver
			continue
		level = status.get(_status.BATTERY_LEVEL)
		if level is not None and level < battery_level:
			battery_status = status
			battery_level = level

	if battery_status is None:
		return _icons.TRAY_OKAY

	assert battery_level < 1000
	charging = battery_status.get(_status.BATTERY_CHARGING)
	icon_name = _icons.battery(battery_level, charging)
	if icon_name and 'missing' in icon_name:
		icon_name = None
	return icon_name or _icons.TRAY_OKAY

#
#
#

def _add_device(icon, device):
	index = None
	for idx, (rserial, _, _, _, _) in enumerate(icon._devices_info):
		if rserial == device.receiver.serial:
			# the first entry matching the receiver serial should be for the receiver itself
			index = idx + 1
			break
	assert index is not None

	# proper ordering (according to device.number) for a receiver's devices
	while True:
		rserial, _, _, number, _ = icon._devices_info[index]
		if rserial == '-':
			break
		assert rserial == device.receiver.serial
		assert number != device.number
		if number > device.number:
			break
		index = index + 1

	device_info = (device.receiver.serial, device.serial, device.name, device.number, device.status)
	icon._devices_info.insert(index, device_info)

	# print ("status_icon: added", index, ":", device_info)

	menu_item = Gtk.ImageMenuItem.new_with_label('    ' + device.name)
	icon._menu.insert(menu_item, index)
	menu_item.set_image(Gtk.Image())
	menu_item.show_all()
	menu_item.connect('activate', icon._menu_activate_callback, device.receiver.path, icon)

	return index


def _remove_device(icon, index):
	# print ("remove device", index)
	assert index is not None
	del icon._devices_info[index]
	menu_items = icon._menu.get_children()
	icon._menu.remove(menu_items[index])


def _add_receiver(icon, receiver):
	device_info = (receiver.serial, None, receiver.name, None, None)
	icon._devices_info.insert(0, device_info)

	menu_item = Gtk.ImageMenuItem.new_with_label(receiver.name)
	icon._menu.insert(menu_item, 0)
	icon_set = _icons.device_icon_set(receiver.name)
	menu_item.set_image(Gtk.Image().new_from_icon_set(icon_set, _MENU_ICON_SIZE))
	menu_item.show_all()
	menu_item.connect('activate', icon._menu_activate_callback, receiver.path, icon)

	icon._devices_info.insert(1, ('-', None, None, None, None))
	separator = Gtk.SeparatorMenuItem.new()
	separator.set_visible(True)
	icon._menu.insert(separator, 1)

	return 0


def _remove_receiver(icon, receiver):
	index = 0
	found = False
	while index < len(icon._devices_info):
		rserial, _, _, _, _ = icon._devices_info[index]
		# print ("remove receiver", index, rserial)
		if rserial == receiver.serial:
			found = True
			_remove_device(icon, index)
		elif found and rserial == '-':
			_remove_device(icon, index)
			break
		else:
			index += 1


def _update_menu_item(icon, index, device_status):
	menu_items = icon._menu.get_children()
	menu_item = menu_items[index]

	image = menu_item.get_image()
	level = device_status.get(_status.BATTERY_LEVEL)
	charging = device_status.get(_status.BATTERY_CHARGING)
	image.set_from_icon_name(_icons.battery(level, charging), _MENU_ICON_SIZE)
	image.set_sensitive(bool(device_status))

#
#
#

def update(icon, device=None):
	# print ("icon update", device, icon._devices_info)

	if device is not None:
		if device.kind is None:
			# receiver
			receiver = device
			if receiver:
				index = None
				for idx, (rserial, _, _, _, _) in enumerate(icon._devices_info):
					if rserial == receiver.serial:
						index = idx
						break

				if index is None:
					_add_receiver(icon, receiver)
			else:
				_remove_receiver(icon, receiver)

		else:
			# peripheral
			index = None
			for idx, (rserial, serial, name, _, _) in enumerate(icon._devices_info):
				if rserial == device.receiver.serial and serial == device.serial:
					index = idx

			if device.status is None:
				# was just unpaired
				assert index is not None
				_remove_device(icon, index)
			else:
				if index is None:
					index = _add_device(icon, device)
				_update_menu_item(icon, index, device.status)

		menu_items = icon._menu.get_children()
		no_receivers_index = len(icon._devices_info)
		menu_items[no_receivers_index].set_visible(not icon._devices_info)
		menu_items[no_receivers_index + 1].set_visible(not icon._devices_info)

	tooltip_lines = _generate_tooltip_lines(icon._devices_info)
	tooltip = '\n'.join(tooltip_lines).rstrip('\n')
	_update_icon(icon, _generate_icon_name(icon), tooltip)

	# print ("icon updated", device, icon._devices_info)
