# pyright: reportMissingModuleSource=false
from algopy import Asset, Global, Txn, UInt64, arc4, gtxn, itxn, op

FOR_SALE_MBR = 2_500 + 64 * 400


class DigitalMarketplace(arc4.ARC4Contract):
    @arc4.abimethod
    def allow_asset(self, mbr_pay: gtxn.PaymentTransaction, asset: Asset) -> None:
        assert not Global.current_application_address.is_opted_in(asset)

        assert mbr_pay.receiver == Global.current_application_address
        assert mbr_pay.amount == Global.asset_opt_in_min_balance

        itxn.AssetTransfer(
            xfer_asset=asset,
            asset_receiver=Global.current_application_address,
            asset_amount=0,
        ).submit()

    @arc4.abimethod
    def first_deposit(
        self,
        mbr_pay: gtxn.PaymentTransaction,
        xfer: gtxn.AssetTransferTransaction,
        nonce: arc4.UInt64,
        unitary_price: arc4.UInt64,
    ) -> None:
        assert mbr_pay.sender == Txn.sender
        assert mbr_pay.receiver == Global.current_application_address
        assert mbr_pay.amount == FOR_SALE_MBR

        box_key = Txn.sender.bytes + op.itob(xfer.xfer_asset.id) + nonce.bytes
        _length, exists = op.Box.length(box_key)
        assert not exists

        assert xfer.sender == Txn.sender
        assert xfer.asset_receiver == Global.current_application_address
        assert xfer.asset_amount > 0

        op.Box.put(box_key, op.itob(xfer.asset_amount) + unitary_price.bytes)

    @arc4.abimethod
    def deposit(self, xfer: gtxn.AssetTransferTransaction, nonce: arc4.UInt64) -> None:
        box_key = Txn.sender.bytes + op.itob(xfer.xfer_asset.id) + nonce.bytes
        _length, exists = op.Box.length(box_key)
        assert exists

        assert xfer.sender == Txn.sender
        assert xfer.asset_receiver == Global.current_application_address
        assert xfer.asset_amount > 0

        current_deposited = op.btoi(op.Box.extract(box_key, 0, 8))
        op.Box.replace(box_key, 0, op.itob(current_deposited + xfer.asset_amount))

    @arc4.abimethod
    def set_price(
        self, asset: UInt64, nonce: arc4.UInt64, unitary_price: arc4.UInt64
    ) -> None:
        box_key = Txn.sender.bytes + op.itob(asset) + nonce.bytes

        op.Box.replace(box_key, 8, unitary_price.bytes)

    @arc4.abimethod
    def withdraw(self, asset: Asset, nonce: arc4.UInt64) -> None:
        box_key = Txn.sender.bytes + op.itob(asset.id) + nonce.bytes

        current_deposited = op.btoi(op.Box.extract(box_key, 0, 8))
        _deleted = op.Box.delete(box_key)

        itxn.Payment(receiver=Txn.sender, amount=FOR_SALE_MBR).submit()

        itxn.AssetTransfer(
            xfer_asset=asset,
            asset_receiver=Txn.sender,
            asset_amount=current_deposited,
        ).submit()

    @arc4.abimethod
    def buy(
        self,
        owner: arc4.Address,
        asset: Asset,
        nonce: arc4.UInt64,
        buy_pay: gtxn.PaymentTransaction,
        quantity: arc4.UInt64,
    ) -> None:
        box_key = owner.bytes + op.itob(asset.id) + nonce.bytes

        current_unitary_price = op.btoi(op.Box.extract(box_key, 8, 8))
        amount_not_scaled_high, amount_not_scaled_low = op.mulw(
            current_unitary_price, quantity.native
        )
        scaling_factor_high, scaling_factor_low = op.expw(10, asset.decimals)
        _quotient_high, amount_to_be_paid, _remainder_high, _remainder_low = op.divmodw(
            amount_not_scaled_high,
            amount_not_scaled_low,
            scaling_factor_high,
            scaling_factor_low,
        )
        assert not _quotient_high

        assert buy_pay.sender == Txn.sender
        assert buy_pay.receiver.bytes == owner.bytes
        assert buy_pay.amount == amount_to_be_paid

        current_deposited = op.btoi(op.Box.extract(box_key, 0, 8))
        op.Box.replace(box_key, 0, op.itob(current_deposited - quantity.native))

        itxn.AssetTransfer(
            xfer_asset=asset,
            asset_receiver=Txn.sender,
            asset_amount=quantity.native,
        ).submit()
